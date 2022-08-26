from collections import defaultdict
from typing import Callable

from discord.ext import commands

from bot.cogs.thread import ThreadData
from bot.core.context import Context
from bot.core.embed import Embed
from bot.mikro import Mikro
from bot.util import database as db


class Parameter:

    def __init__(self, table: str, condition: Callable, query_input: str = None, order_by: Callable = None):
        self.table = table
        self.condition = condition
        self.query_input = query_input
        self.order_by = order_by

    def copy(self, query_input: str):
        return Parameter(self.table, self.condition, query_input)

    def get_condition(self):
        return self.condition(self.query_input)

    def get_order(self):
        if self.order_by is None:
            return None
        return self.order_by(self.query_input)


PARAMETERS = {
    'content': Parameter(
        'thread_messages',
        lambda x: ('message_content_tsv @@ to_tsquery($1)', [' & '.join(x.split(' '))]),
        order_by=lambda x: ('ORDER BY ts_rank(message_content_tsv, to_tsquery($1)', [' & '.join(x.split(' '))])
    )
}


class Query(commands.Cog):

    def __init__(self, parameters: list[Parameter]):
        self.parameters = parameters

    def get_queries(self) -> dict[str, tuple[str, list[object]]]:
        tables = defaultdict(list)
        orders = defaultdict(list)
        for parameter in self.parameters:
            tables[parameter.table].append(parameter.get_condition())
            order = parameter.get_order()
            if order is not None:
                orders[parameter.table].append(order)
        queries = {}
        for table, conds_vars in tables.items():
            variables = []
            i = 0
            conditions = []
            for c, v in conds_vars:
                for num in range(1, len(v) + 1):
                    i += 1
                    c = c.replace('${0}'.format(num), '${0}'.format(i))
                    variables.append(v[num - 1])
                conditions.append(c)
            q = f"SELECT * FROM {table} WHERE {' OR '.join(conditions)}"
            if table in orders:
                q += ' ORDER BY ' + orders[table][0] + ' DESC'
            q += ' LIMIT 15;'
            queries[table] = (q, variables)
        return queries


class Result:

    def __init__(self, thread: ThreadData, message: str, message_id):
        self.thread = thread
        self.message = message
        self.message_id = message_id

    def format_result(self):
        message = self.message.replace('*', '').replace('_', '')
        if len(message) > 20:
            message = message[:20]
        return '[{0}](https://discord.com/channels/{1}/{2}/{3}) ...{4}...'.format(self.thread.title, self.thread.guild.id, self.thread.thread_id, self.message_id, message)


class QueryResult:

    def __init__(self, results: list[Result]):
        self.results = results

    def format_result(self) -> Embed:
        embed = Embed()
        embed.description = '\n'.join([t.format_result() for t in self.results if t.thread.public])
        if not embed.description:
            embed.description = 'None found!'
        return embed


class Search(commands.Cog):

    def __init__(self, bot: Mikro):
        self.bot: Mikro = bot

    @commands.command(name='search')
    async def search_command(self, ctx: Context, *, query: str):
        q = Query([PARAMETERS['content'].copy(query)])
        results = {}
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            for table, q in q.get_queries().items():
                results[table] = await con.fetch(q[0], *q[1])
        format_result = []
        for r in results['thread_messages']:
            format_result.append(Result(await self.bot.thread_handler.get_thread(r['thread']), r['message_content'], r['message_id']))
        qr = QueryResult(format_result)
        await ctx.send(embed=qr.format_result())


async def setup(bot):
    await bot.add_cog(Search(bot))

import discord
from discord.ext import commands
import toml
from bot.util.embed_utils import get_message_kwargs


class Dropdown(discord.ui.Select):
    def __init__(self, reaction_message):
        self.reaction_message = reaction_message

        options = [role.get_option() for role in reaction_message.roles]
        max_val = reaction_message.max_values
        if max_val < 0:
            max_val = len(options)

        super().__init__(placeholder=reaction_message.placeholder, min_values=reaction_message.min_values, max_values=max_val,
                         options=options, custom_id=reaction_message.custom_id)

    async def callback(self, interaction: discord.Interaction):
        await self.reaction_message.callback(interaction, self.values)


class DropdownView(discord.ui.View):

    def __init__(self, reaction_message):
        super().__init__(timeout=None)

        self.add_item(Dropdown(reaction_message))


class Role:

    def __init__(self, name, description, emoji, role_id: int):
        self.name = name
        self.description = description
        self.emoji = emoji
        self.role_id: int = role_id

    def get_option(self):
        return discord.SelectOption(label=self.name, description=self.description, emoji=self.emoji)


class ReactionMessage:

    def __init__(self, bot, custom_id, message, placeholder, min_values, max_values, roles: list[Role]):
        self.bot = bot
        self.custom_id = custom_id
        self.message = message
        self.placeholder = placeholder
        self.roles = roles
        self.min_values = min_values
        self.max_values = max_values
        self.view = DropdownView(reaction_message=self)

    def __getitem__(self, item):
        for r in self.roles:
            if r.name == item:
                return r
        return None

    def get_role(self, role_id):
        return self.bot.get_main_guild().get_role(role_id)

    async def callback(self, interaction: discord.Interaction, values):
        try:
            await self._update_roles(interaction, values)
        except Exception as e:
            await interaction.response.send('Something went wrong!')
            raise e

    async def _update_roles(self, interaction: discord.Interaction, values):
        current = [r.id for r in interaction.user.roles]
        ids = [self[name].role_id for name in values]
        roles: list[discord.Role] = [self.get_role(role_id) for role_id in ids]
        remove = [
            self.get_role(r.role_id) for r in self.roles
            if r.role_id not in ids
            and r.role_id in current
        ]
        if len(remove) > 0:
            await interaction.user.remove_roles(*remove)
        if len(roles) > 0:
            content = 'You selected the role:\n' if len(values) == 1 else 'You selected the roles:\n'
            await interaction.user.add_roles(*roles)
            for role in roles:
                content += '* ' + role.mention + '\n'
            content = content[:-1]
        else:
            content = 'Removed roles!'
        await interaction.response.send_message(
            embed=discord.Embed(title='Roles Updated', description=content),
            ephemeral=True,
        )

    async def send_message(self, channel):
        await channel.send(**get_message_kwargs(self.message), view=self.view)


class Reaction(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.config = toml.load('config/roles.toml')
        self.data = {}

    async def cog_load(self) -> None:
        await self.load_config()

    async def load_config(self):
        for key, value in self.config.items():
            await self.load_reaction(key, value)

    async def load_reaction(self, name, data):
        roles = []
        message = data['data']['message']
        custom_id = data['data']['id']
        placeholder = data['data']['placeholder']
        min_values = data['data']['min']
        max_values = data['data']['max']
        for role in data['roles']:
            roles.append(Role(role['name'], role['description'], role['emoji'], role['role']))
        self.data[name] = ReactionMessage(self.bot, custom_id, message, placeholder, min_values, max_values, roles)
        self.bot.add_view(self.data[name].view)

    @commands.is_owner()
    @commands.command(name='reaction')
    async def reaction(self, ctx, name, channel: discord.TextChannel):
        await self.data[name].send_message(channel)


async def setup(bot):
    await bot.add_cog(Reaction(bot))

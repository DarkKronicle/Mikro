import json

import discord


def get_message_kwargs(data):
    if isinstance(data, str):
        return {'content': data}
    new_data = dict(data)
    kwargs = {}
    if 'content' in new_data:
        kwargs['content'] = new_data.pop('content')
    if len(new_data) > 0:
        kwargs['embed'] = deserialize(new_data)
    return kwargs


def embed_from_answers(answers):
    embed = discord.Embed()
    if answers['title']:
        embed.title = answers['title']
    if answers['footer']:
        embed.set_footer(text=answers['footer'])
    if answers['image']:
        embed.set_image(url=answers['image'])
    if answers['colour']:
        try:
            embed.colour = discord.Colour(int(answers['colour'], 16))
        except:
            pass
    if answers['thumbnail']:
        embed.set_thumbnail(url=answers['thumbnail'])
    if answers['description']:
        embed.description = answers['description']
    if answers['author']:
        embed.set_author(name=answers['author'])
    return embed


def _field_exists(attribute):
    return attribute != discord.Embed.Empty


# Custom deserialization and serialization so that we can restrict embeds
def deserialize(obj_dict):
    embed = discord.Embed()
    title = obj_dict.get('title')
    description = obj_dict.get('description')
    author = obj_dict.get('author')
    footer = obj_dict.get('footer')
    colour = obj_dict.get('colour')
    image = obj_dict.get('image')
    thumbnail = obj_dict.get('thumbnail')
    if title:
        embed.title = title
    if description:
        embed.description = description
    if author:
        embed.set_author(name=author)
    if footer:
        embed.set_footer(text=footer)
    if colour:
        embed.colour = discord.Colour(int(colour, 16))
    if image:
        embed.set_image(url=image)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    return embed


def deserialize_string(string):
    return deserialize(json.loads(string))


def serialize(embed: discord.Embed, **kwargs):
    obj_dict = {}
    if _field_exists(embed.title):
        obj_dict['title'] = embed.title
    if _field_exists(embed.description):
        obj_dict['description'] = embed.description
    if _field_exists(embed.author):
        obj_dict['author'] = embed.author.name
    if _field_exists(embed.footer):
        obj_dict['footer'] = embed.footer.text
    if _field_exists(embed.colour):
        obj_dict['colour'] = embed.colour.int
    if _field_exists(embed.image):
        obj_dict['image'] = embed.image.url
    if _field_exists(embed.thumbnail):
        obj_dict['thumbnail'] = embed.thumbnail.url
    # We don't care for 0 length's
    obj_list = list(
        filter(lambda item: not isinstance(item[1], str) or len(item[1]) > 0, obj_dict.items())
    )
    obj_dict = {}
    for key, value in obj_list:
        if value != discord.Embed.Empty:
            obj_dict[key] = value
    return json.dumps(obj_dict, **kwargs)
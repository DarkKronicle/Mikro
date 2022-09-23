def plural(count: int, word: str):
    if count == 1:
        return word
    return word + 's'


def combine_list_and(entries: list):
    if len(entries) == 0:
        return 'None'
    if len(entries) == 1:
        return entries[0]
    elif len(entries) == 2:
        return entries[0] + ' and ' + entries[1]
    return ', '.join(entries[:-1]) + ', and ' + entries[-1]


def format_code(text: str):
    return ' '.join(t.capitalize() for t in text.split('_'))

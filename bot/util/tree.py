import numpy as np
import random


def get_character(dx, dy, life):
    if dx == 0 and dy == 0 or life == 0:
        return '&'
    if dx == 0 and (dy >= 1 or dy <= -1):
        return '|'
    if dy == 0 and (dx >= 1 or dx <= -1):
        return '~'
    if (dy >= 1 and dx >= 1) or (dy <= -1 and dx <= -1):
        return '/'
    if (dy <= -1 and dx >= 1) or (dy >= 1 and dx <= -1):
        return '\\'
    return '@'


class Bonsai:
    """
    @author https://andai.tv/bonsai/
    """

    def __init__(self, *, width=16, height=32, branch_prob=.05, branch_on_life=5):
        # x, y, (dx, dy)
        self.grid = np.zeros((width, height), dtype=str)
        self.width = width
        self.height = height
        self.branch_prob = branch_prob
        self.branch_on_life = branch_on_life

    def __setitem__(self, key: tuple, value: str):
        try:
            self.grid[key] = value
        except IndexError:
            pass

    def __getitem__(self, item):
        return self.grid[item]

    def run(self, life=15):
        self.branch(self.width // 2, 0, life=life, max_life=life)

    def branch(self, x, y, *, life=15, max_life=15, branches=0):
        branches += 1
        while life > 0:
            dy = -1 if random.random() < .7 else 0
            dx = random.randint(-2,2)
            life -= 1

            if life % 13 == 0 or random.random() < self.branch_prob or life < self.branch_on_life:
                self.branch(x, y, life=life, max_life=max_life, branches=branches)
            x += dx
            y += dy
            char = get_character(dx, dy, life)
            self[x, y] = char

    def __str__(self):
        return self.get_string()

    def get_string(self):
        rows, columns = self.grid.shape
        string = ''
        for y in range(columns):
            for x in range(rows):
                val = self[x, y]
                if val == '':
                    val = ' '
                string += val
            string += '\n'
        return string

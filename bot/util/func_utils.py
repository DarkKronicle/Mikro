def store_func(func, *args, **kwargs):
    def new_func(*newargs, **newkwargs):
        return func(*(args + newargs), **({**kwargs,  **newkwargs}))

    return new_func

import threading


class cached_property(object):  # noqa
    """
    Decorator that converts a method with a single self argument into a
    property cached on the instance.
    Optional ``name`` argument allows you to make cached properties of other
    methods. (e.g.  url = cached_property(get_absolute_url, name='url') )
    """

    def __init__(self, func, name=None):
        self.func = func
        self.__doc__ = getattr(func, '__doc__')
        self.name = name or func.__name__

    def __get__(self, instance, cls=None):
        if instance is None:
            return self
        res = instance.__dict__[self.name] = self.func(instance)
        return res


class thread_cached_property(object):  # noqa
    """
    Decorator that converts a method with a single self argument into a
    property cached on the instance per thread.
    """

    def __init__(self, func, name=None):
        self.func = func
        self.__doc__ = getattr(func, '__doc__')
        self.name = name or func.__name__
        self.cache_name = "__cache_%s" % self.name

    def __get__(self, instance, cls=None):
        if instance is None:
            return self
        # Get threadlocal cache, making it if it doesn't exist
        if not hasattr(instance, self.cache_name):
            setattr(instance, self.cache_name, threading.local())
        cache = getattr(instance, self.cache_name)
        # Get cached result or make it
        if not hasattr(cache, "result"):
            cache.result = self.func(instance)
        return cache.result

import attr


@attr.s
class NamedVolume:
    source = attr.ib()
    mode = attr.ib(default="rw")


@attr.s
class BoundVolume:
    source = attr.ib()
    mode = attr.ib(default="rw")
    required = attr.ib(converter=bool, default=True)


@attr.s
class DevMode:
    source = attr.ib()
    mode = attr.ib(default="rw")

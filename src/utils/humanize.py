def file_size(value, fmt="{value:.1f} {suffix}", si=False):
    """
    Takes a raw number of bytes and returns a humanized filesize.
    """
    if si:
        base = 1000
        suffixes = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    else:
        base = 1024
        suffixes = ("B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB")
    max_suffix_index = len(suffixes) - 1
    for i, suffix in enumerate(suffixes):
        unit = base ** (i + 1)
        if value < unit or i == max_suffix_index:
            return fmt.format(value=(base * value / unit), suffix=suffix)

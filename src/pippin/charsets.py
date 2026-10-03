"""Charset ramps, dark -> light."""

ASCII_RAMP = " .:-=+*#%@"

UTF8_RAMP = " `^\",:;Il!i~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"

BLOCKS_RAMP = " ░▒▓█"

CHARSETS = {
    "ascii": ASCII_RAMP,
    "utf8": UTF8_RAMP,
    "blocks": BLOCKS_RAMP,
}


def get_ramp(name: str = "utf8", custom: str | None = None, invert: bool = False) -> str:
    """Resolve a luminance ramp.

    Args:
        name: one of 'ascii' | 'utf8' | 'blocks'.
        custom: explicit ramp string, overrides name.
        invert: reverse the ramp (light -> dark).
    """
    if custom is not None:
        if len(custom) < 2:
            raise ValueError("--custom-chars must contain at least 2 characters")
        ramp = custom
    else:
        try:
            ramp = CHARSETS[name]
        except KeyError:
            raise ValueError(f"unknown charset {name!r}, expected one of {sorted(CHARSETS)}")
    if invert:
        ramp = ramp[::-1]
    return ramp

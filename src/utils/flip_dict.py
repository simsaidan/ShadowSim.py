def flip_dict(d):
    """
    Return a new dictionary with each string key reversed.

    This is used to switch the endianness of measurement results.
    """
    return {k[::-1]: v for k, v in d.items()}


VERSION = (0, 9, 1)
__version__ = '.'.join(map(str, VERSION))


try:
    #build distribution will fail, since maya modules aren't present.
    #ad the toml gets the versioning info from the module.
    from .core import *
except ModuleNotFoundError:
    pass


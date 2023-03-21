

VERSION = (0, 9, 0)
__version__ = '.'.join(map(str, VERSION))


try:
    from .core import *
except:    
    pass

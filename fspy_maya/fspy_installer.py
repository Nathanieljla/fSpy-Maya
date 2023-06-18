"""
Drag-n-drop this into a maya viewport to install the packages
"""
import os
import re
import time
import platform
import sys
import webbrowser
import base64
#import math
#from datetime import datetime, timedelta
import glob
import tempfile
import shutil
import sys
import subprocess
from os.path import expanduser
import zipfile
from functools import partial
import site

try:
    #python3
    from urllib.request import urlopen
except:
    #python2
    from urllib import urlopen

try:
    #python2
    reload
except:
    #python3
    from importlib import reload

try:
    import maya.utils
    import maya.cmds
    from maya import OpenMayaUI as omui
    
    from PySide2.QtCore import *
    from PySide2.QtWidgets import *
    from PySide2.QtGui import *
    from shiboken2 import wrapInstance
    MAYA_RUNNING = True
except ImportError:
    MAYA_RUNNING = False
    

RESOURCES = None
    
class Platforms(object):
    OSX = 0,
    LINUX = 1,
    WINDOWS = 2
    
    @staticmethod
    def get_name(enum_value):
        if enum_value == Platforms.OSX:
            return 'osx'
        elif enum_value == Platforms.LINUX:
            return 'linux'
        else:
            return 'windows'

        
class Module_definition(object):
    """A .mod file can have multiple entries.  Each definition equates to one entry"""
    
    MODULE_EXPRESSION = r"(?P<action>\+|\-)\s*(MAYAVERSION:(?P<maya_version>\d{4}))?\s*(PLATFORM:(?P<platform>\w+))?\s*(?P<module_name>\w+)\s*(?P<module_version>\d+\.?\d*.?\d*)\s+(?P<module_path>.*)\n(?P<defines>(?P<define>.+(\n?))+)?"
        
    def __init__(self, module_name, module_version,
                 maya_version = '', platform = '',
                 action = '+', module_path = '',
                 defines = [],
                 *args, **kwargs):
        
        self.action = action
        self.module_name = module_name
        self.module_version = module_version
        
        self.module_path = r'.\{0}'.format(self.module_name)
        if module_path:
            self.module_path = module_path

        self.maya_version = maya_version
        if self.maya_version is None:
            self.maya_version = ''
        
        self.platform = platform
        if self.platform is None:
            self.platform = ''
        
        self.defines = defines
        if not self.defines:
            self.defines = []
        
    def __str__(self):
        return_string = '{0} '.format(self.action)
        if self.maya_version:
            return_string += 'MAYAVERSION:{0} '.format(self.maya_version)
            
        if self.platform:
            return_string += 'PLATFORM:{0} '.format(self.platform)
            
        return_string += '{0} {1} {2}\n'.format(self.module_name, self.module_version, self.module_path)
        for define in self.defines:
            if define:
                return_string += '{0}\n'.format(define.rstrip('\n'))
         
        return_string += '\n'    
        return return_string


class Module_manager(QThread):
    """Used to edit .mod files quickly and easily."""
    
    def __init__(self, module_name, module_version, package_name='',
                 include_site_packages = False):
        
        QThread.__init__(self)
        self.install_succeeded = False
        
        self._module_definitions = []
        self.module_name = module_name
        self.module_version = module_version
        
        self.package_name = package_name
        if not self.package_name:
            self.package_name = self.module_name
        
        self.maya_version = self.get_app_version()
        self.platform = self.get_platform()
        
        self.max, self.min, self.patch = sys.version.split(' ')[0].split('.')
        self.max = int(self.max)
        self.min = int(self.min)
        self.patch = int(self.patch)
        
        #common locations
        self._version_specific = self.is_version_specific()  
        self.app_dir = os.getenv('MAYA_APP_DIR')
        self.install_root = self.get_install_root()
        self.relative_module_path = self.get_relative_module_path()
        self.module_path = self.get_module_path()
        self.icons_path = self.get_icon_path()
        self.presets_path = self.get_presets_path()
        self.scripts_path = self.get_scripts_path()
        self.plugins_path = self.get_plugins_path()
        
        self.site_packages_path = self.get_site_package_path()
        if not include_site_packages:
            self.site_packages_path = ''
            
        self.package_install_path = self.get_package_install_path()
        
        #Non-Maya python and pip paths are needed for installing on linux (and OsX?)
        self.python_path = ''
        self.pip_path = ''
        self.__find_python_paths()
        self.uses_global_pip = False
        self.command_string = self._get_command_string()
        
        
    def __del__(self):
        self.wait()
        
        
    def __ensure_pip_exists(self):
        """Make sure OS level pip is installed
        
        This is written to work with all platforms, but
        I've updated this to only run when we're on linux
        because it sounds like that's the only time it's needed
        """
        
        if not self.uses_global_pip:
            print("Using Maya's PIP")
            return
        
        if os.path.exists(self.pip_path):
            print('Global PIP found')
            return
        
        tmpdir = tempfile.mkdtemp()
        get_pip_path = os.path.join(tmpdir, 'get-pip.py')
        print(get_pip_path)
        
        if self.platform == Platforms.OSX:
            #cmd = 'curl https://bootstrap.pypa.io/pip/{0}/get-pip.py -o {1}'.format(pip_folder, pip_installer).split(' ')
            cmd = 'curl https://bootstrap.pypa.io/pip/get-pip.py -o {0}'.format(get_pip_path).split(' ')
            self.run_shell_command(cmd, 'get-pip')

        else:
            # this should be using secure https, but we should be fine for now
            # as we are only reading data, but might be a possible mid attack
            #response = urlopen('https://bootstrap.pypa.io/pip/{0}/get-pip.py'.format(pip_folder))
            response = urlopen('https://bootstrap.pypa.io/pip/get-pip.py')
            data = response.read()
            
            with open(get_pip_path, 'wb') as f:
                f.write(data)
                
        # Install pip
        # On Linux installing pip with Maya Python creates unwanted dependencies to Mayas Python version, so pip might not work 
        # outside of Maya Python anymore. So lets install pip with the os python version. 
        filepath, filename = os.path.split(get_pip_path)
        #is this an insert, so this pip is found before any other ones?
        sys.path.insert(0, filepath)
        
        
        if self.platform == Platforms.OSX or self.platform == Platforms.LINUX:
            python_str = 'python{0}.{1}'.format(self.max, self.min)
        else:
            python_str = self.python_path
            
        cmd = '{0}&{1}&--user&pip'.format(python_str, get_pip_path).split('&')
        self.run_shell_command(cmd, 'install pip')
        
        print('Global PIP is ready for use!')
        
        
    def __find_python_paths(self):      
        version_str = '{0}.{1}'.format(self.max, self.min)
        if self.platform == Platforms.WINDOWS:
            self.python_path = os.path.join(os.getenv('MAYA_LOCATION'), 'bin', 'mayapy.exe')
            if self.max > 2:
                #python3 pip path
                self.pip_path = os.path.join(os.getenv('APPDATA'), 'Python', 'Python{0}{1}'.format(self.max, self.min), 'Scripts', 'pip{0}.exe'.format(version_str))
            else:
                #python2 pip path
                self.pip_path = os.path.join(os.getenv('APPDATA'), 'Python', 'Scripts', 'pip{0}.exe'.format(version_str))

        elif self.platform == Platforms.OSX:
            self.python_path = '/usr/bin/python'
            self.pip_path = os.path.join( expanduser('~'), 'Library', 'Python', version_str, 'bin', 'pip{0}'.format(version_str) )
     
        elif self.platform == Platforms.LINUX:
            self.python_path = os.path.join(os.getenv('MAYA_LOCATION'), 'bin', 'mayapy')
            self.pip_path = os.path.join( expanduser('~'), '.local', 'bin', 'pip{0}'.format(version_str) )
            
            
    def _get_command_string(self):
        """Creates the commandline string for launching pip commands
        
        If the end-user is on linux then is sounds like calling pip from Mayapy
        can cause dependencies issues when using a default python install.
        So if the user is on osX or windows OR they're on linux and don't
        have python installed, then we'll use "mayapy -m pip" else we'll
        use the pipX.exe to run our commands.        
        """
        command = '{0}&-m&pip'.format(self.python_path)
        if self.platform == Platforms.LINUX:
            try:
                Module_manager.run_shell_command(['python'], 'Checking python install')
                command = self.pip_path
                self.uses_global_pip = True
            except:
                #Python isn't installed on linux, so the default command is good
                pass
            
        return command
        
        
    def is_version_specific(self):
        """Is this install for a specific version of Maya?
        
        Some modules might have specific code for different versions of Maya.
        For example if Maya is running Python 3 versus. 2. get_relative_module_path()
        returns a different result when this True vs.False unless overridden by
        the user.
        
        Returns:
        --------
        bool
            False
        """        
        
        return False
     
    def get_install_root(self):
        """Where should the module's folder and defintion install?
        
        Maya has specific locations it looks for module defintitions os.getenv('MAYA_APP_DIR')
        For windows this is "documents/maya/modules" or "documents/maya/mayaVersion/modules"
        However 'userSetup' files can define alternative locations, which is
        good for shared modules in a production environment.
        
        Returns:
        --------
        str
            os.path.join(self.app_dir, 'modules')
        """        
        return os.path.join(self.app_dir, 'modules')
    
    def get_relative_module_path(self):
        """What's the module folder path from the install root?
        
        From the install location we can create a series of folder to reach
        the base of our module.  This is where Maya will look for the
        'plug-ins', 'scripts', 'icons', and 'presets' dir.  At a minimum
        you should return the name of your module. The default implementation
        create as a path of 'module-name'/platforms/maya-version/platform-name/x64
        when is_version_specific() returns True
        
        Returns:
        str
            self.module_name when is_version_specific() is False
        
        """
        root = self.module_name
        if self._version_specific:
            root = os.path.join(self.module_name, 'platforms', str(self.maya_version),
                                Platforms.get_name(self.platform),'x64')  
        return root
    
    def get_module_path(self):
        return os.path.join(self.install_root, self.relative_module_path)
    
    def get_icon_path(self):
        return os.path.join(self.module_path, 'icons')
    
    def get_presets_path(self):
        return os.path.join(self.module_path, 'presets')
    
    def get_scripts_path(self):
        return os.path.join(self.module_path, 'scripts')
    
    def get_plugins_path(self):
        return os.path.join(self.module_path, 'plug-ins')
    
    def get_site_package_path(self):
        return os.path.join(self.scripts_path, 'site-packages')
    
    def get_package_install_path(self):
        return os.path.join(self.scripts_path, self.module_name)
    
  
    def read_module_definitions(self, path):
        self._module_definitions = []
        if (os.path.exists(path)):
            file = open(path, 'r')
            text = file.read()
            file.close()
          
            for result in re.finditer(Module_definition.MODULE_EXPRESSION, text):
                resultDict = result.groupdict()
                if resultDict['defines']:
                    resultDict['defines'] = resultDict['defines'].split("\n")
                    
                definition = Module_definition(**resultDict)
                self._module_definitions.append(definition)
      
                        
    def write_module_definitions(self, path):
        file = open(path, 'w')
        for entry in self._module_definitions:
            file.write(str(entry))
        
        file.close()

                           
    def __get_definitions(self, search_list, key, value):
        results = []
        for item in search_list:
            if item.__dict__[key] == value:
                results.append(item)
                
        return results
        
          
    def _get_definitions(self, *args, **kwargs):
        result_list = self._module_definitions
        for i in kwargs:
            result_list = self.__get_definitions(result_list, i, kwargs[i])
        return result_list
    
    
    def remove_definitions(self, *args, **kwargs):
        """
        removes all definitions that match the input argument values
        example : module_manager_instance.remove_definitions(module_name='generic', platform='win', maya_version='2023')
        
        Returns:
        --------
        list
            the results that were removed from the manager.
        
        """ 
        results = self._get_definitions(**kwargs)
        for result in results:
            self._module_definitions.pop(self._module_definitions.index(result))
            
        return results
    
    
    def remove_definition(self, entry):
        self.remove_definitions(module_name=entry.module_name,
                                platform=entry.platform, maya_version=entry.maya_version)
    
    def add_definition(self, definition):
        """

        """
        #TODO: Add some checks to make sure the definition doesn't conflict with an existing definition
        self._module_definitions.append(definition)
        
    @staticmethod
    def get_app_version():
        return int(str(maya.cmds.about(apiVersion=True))[:4])
    
    @staticmethod
    def get_platform_string(platform):
        if platform is Platforms.OSX:
            return 'mac'
        elif platform is Platforms.LINUX:
            return 'linux'
        else:
            return 'win64'
    
    @staticmethod
    def get_platform():
        result = platform.platform().lower()
        if 'darwin' in result:
            return Platforms.OSX
        elif 'linux' in result:
            return Platforms.LINUX
        elif 'window' in result:
            return Platforms.WINDOWS
        else:
            raise ValueError('Unknown Platform Type:{0}'.format(result))
    
    @staticmethod
    def make_folder(folder_path):
        print(folder_path)
        
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)

    @staticmethod
    def get_ui_parent():
        return wrapInstance( int(omui.MQtUtil.mainWindow()), QMainWindow )      
 

    @staticmethod    
    def run_shell_command(cmd, description):
        #NOTE: don't use subprocess.check_output(cmd), because in python 3.6+ this error's with a 120 code.
        print('\n{0}'.format(description))
        print('Calling shell command: {0}'.format(cmd))

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = proc.communicate()
        stdout = stdout.decode()
        stderr = stderr.decode()
        
        print(stdout)
        print(stderr)
        if proc.returncode:
            raise Exception('Command Failed:\nreturn code:{0}\nstderr:\n{1}\n'.format(proc.returncode, stderr))
        
        return(stdout, stderr)
        
   
    def run(self):
        """this starts the QThread"""
        try:
            self.install_succeeded = self.install()
        except Exception as e:
            self.install_succeeded = False
            print('Install Failed!!\n{0}'.format(e))
            
                 
    def get_definition_entry(self):
        """Converts this class into a module_defintion
        
        Returns:
        --------
        Module_definition
            The module defintion that represents the data of the Module_manager
        
        """
        maya_version = str(self.maya_version)
        
        python_path =  'PYTHONPATH+:={0}'.format(self.site_packages_path.split(self.module_path)[1])
        relative_path = '.\{0}'.format(self.relative_module_path)        
        platform_name =  self.get_platform_string(self.get_platform())
        
        if not self._version_specific:
            maya_version = ''
            platform_name = ''
            
        defines = []
        if self.site_packages_path:
            defines = [python_path]
        
        module_definition = Module_definition(self.module_name, self.module_version,
                                                             maya_version=maya_version, platform=platform_name, 
                                                             module_path=relative_path,
                                                             defines=defines)
        return module_definition
     
             
    def update_module_definition(self, filename):
        """remove old defintions and adds the current defintion to the .mod
        
        Returns:
        --------
        bool
            True if the update was successful else False        
        """
        new_entry = self.get_definition_entry()
        self.remove_definition(new_entry) #removes any old entries that might match before adding the new one
        self.add_definition(new_entry)  
        try:
            self.write_module_definitions(filename)
        except IOError:
            return False
        
        return True
        

    def pre_install(self):
        """Called before install() to do any sanity checks and prep
        
        This function attempts to create the required install folders
        and update/add the .mod file. Sub-class should call this function
        when overriding

        Returns:
        --------
        bool
            true if the install can continue
        """
        try:
            self.__ensure_pip_exists()

        except Exception as e:
            print('failed to setup global pip {0}'.format(e))
            return False
        
        try:          
            self.make_folder(self.module_path)       
            self.make_folder(self.icons_path)
            self.make_folder(self.presets_path)
            self.make_folder(self.scripts_path)
            self.make_folder(self.plugins_path)
            
            if self.site_packages_path:
                self.make_folder(self.site_packages_path)
        except OSError:
            return False

        filename = os.path.join(self.install_root, (self.module_name + '.mod'))
        self.read_module_definitions(filename)
              
        return self.update_module_definition(filename)
    

    def install(self):
        """The main install function users should override"""        
        pass
    
    def post_install(self):
        """Used after install() to do any clean-up

        """  
        pass
    
    
##-----begin UI----##
    
class IconButton(QPushButton):
    def __init__(self, text, highlight=False, icon=None, success=False, *args, **kwargs):
        super(IconButton, self).__init__(QIcon(icon), text, *args, **kwargs)

        self.icon = icon
        self.highlight = highlight
        self.success = success
        self.setMinimumHeight(34)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        if self.highlight:
            self.setStyleSheet('QPushButton{color: #161a1d; background-color: #00a07b; border: none; border-radius: 3px; padding: 10px;} QPushButton:hover {background-color: #00c899}')
            font = self.font()
            font.setPointSize(14)
            font.setBold(True)
            self.setFont(font)

        if self.success:
            self.setStyleSheet('QPushButton{color: #161a1d; background-color: #dfefd9; border: none; border-radius: 3px; padding: 10px;}')
            font = self.font()
            font.setPointSize(14)
            font.setBold(True)
            self.setFont(font)

        if self.icon:
            self.setIconSize(QSize(22, 22))
            self.setIcon(QIcon(self.AlphaImage()))

    def AlphaImage(self):
        if self.highlight and not self.success:
            AlphaImage = QPixmap(self.icon)
            painter = QPainter(AlphaImage)

            painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
            painter.fillRect(AlphaImage.rect(), '182828')

            return AlphaImage

        else:
            return QPixmap(self.icon)
        
     

class Resources(object):
    preloaderAnimBase64 = '''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'''
    BYTE_GIF = QByteArray.fromBase64( preloaderAnimBase64.encode() )
    
    company_base64 = None
    install_base64 = '''iVBORw0KGgoAAAANSUhEUgAAAFgAAABYCAYAAABxlTA0AAAABHNCSVQICAgIfAhkiAAAAAlwSFlzAAALEwAACxMBAJqcGAAAA2NJREFUeJztnN9RGzEQh3+ryTvuIHQAqSCOzn4OJUAFoYO4BKeCpAR4PkvjdGA6oATTgDYvx4xjwv3x7Z7kyX5v3N5I6w8h6eQ9AMMwDMMwDMMwDMMwDMMwDON/gHIn0JcY4+fDn733v3PlMoTiBdd1feGcewYwO7zOzNvFYvElT1b9cbkT6MI5t8aRXAAgonkI4XuGlAZRvGAANy2x+8myOJFzEPxm9PaMFcE5CD5rTLAyJlgZE6yMCVbGBCtjgpX5oNHoZrP5hr8fEPbOuZX3/kmjv6HEGK9SSuvDa865tff+Ubov8bOIGONXZn74R+g5pXS9XC5fhrQXQuC2eFVVgz5Dc7axA3B5FNoT0Vx6EIhPESml1TuhSyLa1nV9Id1nX+q6viCiLd7KBYDZ8aiWQFwwEV23xXJJfpXbkd9cut/JF7kckvvI1UJcMDNvu+6ZUvIQuX1yH4q4YOfcPYB9131TSB44cvdN7qKIC/bePzVzWVbJQ+Vq7CAApTk4t+RS5AKKi1wuySXJBZR3EVNLLk0uMME2bSrJJcoFJtoHa0suVS4wcV1EjPGq2Wt2flnJzDtmnjvnWn8pKaVZqXKBDIUnQyV3ietzT8PkcoFMlT1DJAuRRS6QsXRqQsnZ5AKZa9MmkJxVLlBA8Z+i5OxygQIEAyqSi5ALFCIYEJVcjFygIMGAiOSi5AKFCQZGSS5OLiAoWLLE/wTJo+VqvaIwWrBWif8AyaPkar+iMPqwR6vEv+cB0eiRq/2KgsRpmlqJfyP59p2w1Jyr+oqChGDVEn/v/SMRXTPz7vUaM29TSpdCC5pq/iq1adI0Ij/lzuMU1A/cY4xX2n2cyvHOQYPRgruKNVJK87F9aJFSap1jJQpRRk8RRPTcEV9tNhsw86+hlZVahBA+MvOaiNoWOBDRri3eh9GCmXnbstIDwIyI1kS0DiGM7U4Mou5HgKYScxQSU8QDenyZeYbsJQqyRwtu/uzF62pzw8wriXZEdhEppfXhPvXcYebdYrH4IdGWiODlcvnCzHON8s+pYeYtM8+l2hM/rgwh/ARwK93uRPyqqupOskHxB42qqu6Y+RZntvAx8720XEDxwL0pZ7oBcNOcihX3rweaKe2hpD26YRiGYRiGYRiGYRiGYRiGYRiGYRjD+AN6etoeN+hk/AAAAABJRU5ErkJggg=='''
    close_base64 = '''iVBORw0KGgoAAAANSUhEUgAAAFgAAABYCAYAAABxlTA0AAAABHNCSVQICAgIfAhkiAAAAAlwSFlzAAALEwAACxMBAJqcGAAAA7lJREFUeJztm8tx2zAQhv9lA3YHdiqwO4iGpM5xB6Y7UAdRKohSQeQO5DMfo3Qgd6B0IDfAzSHgjOwhJQDCgvTMfleCXPIbEI8FACiKoiiKoiiKoiiKoiiKoiiKoiiKoijKECT14LqubwAUzDwDACLatW27nM/nb1IxbWia5o6ZF8x8a95rT0SrNE1fJeKJCK7r+ieARc+ldZZlTxIxbSjL8oqItkR0//EaEd1LSA4u2NSQ3Yki67ZtF7Frcl3XN8y86ZNr2GdZ9iV03CT0A5n54UyRgoi2ZVlehY49RNM0dwB2J+QCwK1EbAnBh3NliOg+lmTzR20BXEvH6iO44CRJtjblYkh2kXumWfMmuOA0TV+ZeWNTlojukyTZm184KFVVPRpptjV3HfodAAHBAMDMhUONuGbmbUjJVVU9EtHa4ZZ1nue/QsU/RkTwfD5/Y+aZ+T1tCCbZQ+5KcugoNtHoqOv6N4DCsviBmRd5nj97xhoaf/fCzIVvLFvEBQPOkr0+PEYMH6IIBmQFTFUuEFEw4NU+LrMs+zF00Ux910R0bnLTcSCimVTeoY+oggG/Hr6vEzqVVxggulxgBMHA5ZI/i1xgJMEA0DTNVzMhsZ4ItG27SJLk+kzS5h3MvCOihyzL/vq/rT+jCQbc8wRG1q1LeWaejZmDHlUwIJeMmYJcQGgm50Kapq9ENAuZbGHmzRTkAhOowR0eHdcQo66afGQygoEgkiclF5hAE3GMR5LoGNGkjS+TEgz8l0xEW8fbDh73RGFSTQTgnlc4JmaOwZZJCb5EbsfUJE9CcFmWV0mSrHCh3A6TUxZZoXBldMEBh2cfmcSIYtROzidp4/D4wjQ5ozKaYFe5Jg8xM7lfW9GjSx6lifBJ8hxPfS+9PybRBYeS81kkR20iPKRsh6R0SSIAe5tnxdyu9S5urEBmFWMFhwS7zSjAo6PcE9FDrNWNKIJDrcMNMeUlJHHB0nI7pipZVHBd198BLG3Lh5jmuu4kIqIiTdOXS2KeQvKMxmibQaa0EUVEsGuzIPGBrpJNxxe8JosM04hoaVn0QEQzidqTZdkTM1tvBGzbdhn6HQABwVVVPcLuvEPXyfwJ/Q4deZ7/YubCpqxAsgmAgGCzb+Ec0YZJeZ4/20qWQELwyeMDXdIm5jamPM+fLZJEe4nYImc0AKz6rnX5gDH2iKVp+mKm1n2S9w47NJ0QG6Y1TfOtbdvjTmbNzJuxN4P0HPHdj3EwUlEURVEURVEURVEURVEURVEURVEURVGAf9l4XANGvwF5AAAAAElFTkSuQmCC'''

    def __init__(self):
        super(Resources, self).__init__()        
        self.installer = None
        
    def __del__(self):
        if self.installer:
            self.installer.deleteLater()
             
    @staticmethod
    def base64_to_QPixmap(base64Image):
        pixmap = QPixmap()
        byte_array =  QByteArray.fromBase64( base64Image.encode() )
        pixmap.loadFromData(byte_array)
        
        return QPixmap(pixmap)
    
    @staticmethod
    def qPixmap_to_base64(pixmap, extension):
        #https://doc.qt.io/qtforpython/index.html
        #https://forum.qt.io/topic/85064/qbytearray-to-string/2
        image = pixmap.toImage()
        byteArray = QByteArray()
        buffer = QBuffer(byteArray)
        image.save(buffer, "png")
        base64 = byteArray.toBase64().data()
        result = str(base64, encoding='utf-8')
            
        return result
            
    @staticmethod
    def file_to_base64(file_path):
        extension = os.path.basename(file_path).split('.')[-1]
        pixmap = QPixmap()
        if pixmap.load(file_path):
            return Resources.qPixmap_to_base64(pixmap, extension)
        else:
            return ''

    
    def set_installer(self, installer):
        self.installer = installer
    
    
    @property
    def close_icon(self):        
        return self.base64_to_QPixmap(Resources.close_base64)
    
    @property
    def install_icon(self):        
        return self.base64_to_QPixmap(Resources.install_base64)
              
    @property
    def company_icon(self):
        result = None
        if Resources.company_base64:
            result = self.base64_to_QPixmap(Resources.company_base64)
        
        return result
    
    @company_icon.setter
    def company_icon(self, value):
        Resources.company_base64 = value
      
    
class Installer_UI(QWidget):
    def __init__(self, name, module_manager, background_color = '', company_logo_size = [64, 64], *args, **kwargs):
        self.module_manager = module_manager
        parent = module_manager.get_ui_parent()
        super(Installer_UI, self).__init__(parent=parent, *args, **kwargs)
        
        self.create_layout(background_color, company_logo_size)
        self.set_default_size(name)
        self.install_button.clicked.connect(self.on_install)
        self.close_button.clicked.connect(self.on_close)

    def set_default_size(self, name):
        size = [10, 10]
        width = size[0]
        height = size[1]    
        desktop = QApplication.desktop()
        screenNumber = desktop.screenNumber(QCursor.pos())
        screenRect = desktop.screenGeometry(screenNumber)
        widthCenter = screenRect.width() / 2 - width / 2
        heightCenter = screenRect.height() / 2 - height / 2
        
        self.animated_gif.hide()
        self.wait_label.hide()        
        self.setGeometry(QRect(widthCenter, heightCenter, width, height))
               
        self.setObjectName(name)
        self.setWindowTitle(name)
        self.setWindowModality(Qt.ApplicationModal)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setWindowFlags(Qt.Tool)
        self.setFixedSize(self.layout().minimumSize())
        self.close_button.hide()
        
        
    def create_layout(self, background_color, company_logo_size):
        #background color
        if background_color:
            palette = self.palette()
            palette.setColor(self.backgroundRole(), background_color)
            self.setPalette(palette)             
        
        ##-----create all our ui elements THEN arrange them----##
        logo = None

        if RESOURCES.company_icon is not None:
            logo = QLabel()
            smallLogo = RESOURCES.company_icon.scaled(company_logo_size[0], company_logo_size[1], Qt.KeepAspectRatio, Qt.SmoothTransformation)
    
            logo.setPixmap(smallLogo)
            logo.setAlignment(Qt.AlignCenter | Qt.AlignCenter)
            logo.setMargin(15)

        self.install_button = IconButton('Install', highlight=True) #, icon=RESOURCES.install_icon)
        self.install_button.setMinimumHeight(42)
        self.close_button = IconButton(' Close', icon=RESOURCES.close_icon)
        self.close_button.setMinimumHeight(42)

        self.wait_label = QLabel()
        self.wait_label.setText('Installing, please wait ...')
        
        self.movie = QMovie()
        self.device = QBuffer(Resources.BYTE_GIF)
        self.movie.setDevice(self.device)
        self.animated_gif = QLabel()

        self.animated_gif.setMovie(self.movie)
        self.animated_gif.setMaximumHeight(24)
        self.animated_gif.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.animated_gif.setScaledContents(True)
        self.animated_gif.setMaximumWidth(24)
        outer = QVBoxLayout()
        self.setLayout(outer)
        if logo:
            outer.addWidget(logo, 0)
            
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.install_button, 0)
        button_layout.addWidget(self.close_button, 0)
        button_layout.addWidget(self.animated_gif, 0)
        button_layout.addWidget(self.wait_label, 0)
        button_layout.addStretch()
        button_layout.setAlignment(Qt.AlignCenter)
        outer.addLayout(button_layout)
                
    def on_install(self):
        self.install_button.hide()
        #self.movie.start() #I'm thinking this causes maya to crash when debugging in WING
        self.animated_gif.show()
        self.wait_label.show()
        
        if self.module_manager.pre_install():
            self.connect(self.module_manager, SIGNAL('finished()'), self.done)
            self.module_manager.start()
        
    
    def done(self):
        self.close_button.show()
        self.animated_gif.hide()
        self.wait_label.hide()
        
        self.module_manager.post_install()
    
        
    def on_close(self):
        self.close()
        
    def clean(self):
        self.movie.stop()
        if self.device.isOpen():
            self.device.close()

    def closeEvent(self, event):
        self.clean()
        
        
        
        
class Custom_Installer(Module_manager):
    def __init__(self, *args, **kwargs):
        super(Custom_Installer, self).__init__(*args, **kwargs)
        
                
    @staticmethod
    def pip_install(pip_command, repo_name, pip_args = [], *args, **kwargs):
        cmd_str = ('{0}&install&{1}').format(pip_command, repo_name)
        args = cmd_str.split('&') + pip_args
        stdout, stderr = Module_manager.run_shell_command(args, 'PIP:Installing Package')
        
        return stdout

    @staticmethod
    def pip_list(pip_command, pip_args = [], *args, **kwargs):
        cmd_str = ('{0}&list').format(pip_command)
        args = cmd_str.split('&') + pip_args
        stdout, stderr = Module_manager.run_shell_command(args, 'PIP:Listing Packages')
        
        return stdout    

    @staticmethod
    def pip_show(pip_command, repo_name, pip_args = [], *args, **kwargs):
        cmd_str = ('{0}&show&{1}').format(pip_command, repo_name)
        args = cmd_str.split('&') + pip_args
        stdout, stderr = Module_manager.run_shell_command(args, 'PIP:Show Package Info')
        
        return stdout
    
    
    def get_pip_list(self, *args, **kwargs):
        result = Custom_Installer.pip_list(self.command_string, *args, **kwargs)
        return result
        
    
    def get_pip_show(self, *args, **kwargs):
        result = Custom_Installer.pip_show(self.command_string, self.package_name, *args, **kwargs)
        return result
    

    def install_package(self):
        #https://stackoverflow.com/questions/39365080/pip-install-editable-with-a-vcs-url
        #github = r'https://github.com/Nathanieljla/fSpy-Maya.git'
        
        pip_args = [
            #r'--user', 
            #r'--editable=git+{0}#egg={1}'.format(github, self.repo_name), 
            r'--target={0}'.format(self.scripts_path), 
        ]
        self.pip_install(self.command_string, self.get_remote_package(), pip_args)
    
    
    def package_installed(self):
        """returns True if the repo is already on the system"""
        return self.get_pip_list().find(self.package_name) != -1
    

    def package_outdated(self):
        """Check to see if a local package is outdated
        
        Checks to see the local pacakge is out-of-date.  This will always
        be true with remote packages that are from Git, but will be accurate
        with packages registered on PyPi. Since package_outdated()
        assumes the package exists before checking make sure you you first
        check the existance of the package with package_installed() before
        checking the outdated status.
        
        Returns:
        --------
        bool
            True if missing or outdated, else False
        """
        #TODO: get version checking to work with git packages.
        #https://stackoverflow.com/questions/11560056/pip-freeze-does-not-show-repository-paths-for-requirements-file
        #https://github.com/pypa/pip/issues/609
        #it looks like we'd have to install packages with pip -e for this to work,
        #but then we can't install to a target dir. I'm getting errors about
        #trying to install in maya/src, but --user doesn't work either.

        #I'm using --uptodate here, because both --uptodate and --outdated
        #will be missing the package if the pacakage isn't registered with PyPi
        #so -uptodate is easier to verify with than -o with remote package that
        # might or might not be registered with PyPi
        result = self.get_pip_list(pip_args =['--uptodate'])
        outdated = result.find(self.package_name) == -1
        if outdated:
            return True
        else:
            return False

    
    
    def get_remote_package(self):
        """returns the github or PyPi name needed for installing"""
        
        return r'https://github.com/Nathanieljla/fSpy-Maya/archive/refs/heads/main.zip'
        
        #dev_path = r'C:\Users\natha\Documents\github\fSpy-Maya'
        #if os.path.exists(dev_path):
            #return r'git+file:///{0}'.format(dev_path)
        #else:
            #return r'https://github.com/Nathanieljla/fSpy-Maya/archive/refs/heads/main.zip'
    
    
##--------------move the above into Module_manager
            
            
    #def get_relative_module_path(self):
        #base = super(Custom_Installer, self).get_relative_module_path()
        #return os.path.join(base, 'local_install')
    
    #def get_scripts_path(self):
        #return os.path.join(self.module_path, 'local_install')
               
        
    def pre_install(self):
        result = super(Custom_Installer, self).pre_install()
        return result
        
        
    def install(self):
        """The main install function users should override
        
        Users must return True or False to indicate if the installation was a succcess        
        """

        installed = False
        if not self.package_installed() or self.package_outdated():
            #this might be a re-install, so lets try unloading the plug-in to be clean
            try:                    
                maya.cmds.unloadPlugin('fspy_plugin')
            except Exception as e:
                pass          
            
            try:
                self.install_package()
                installed = True
            except:
                pass
            
        return installed
            

    
    def post_install(self):
        """Used after install() to do any clean-up

        """  
        print('post install')
        if self.install_succeeded:
            #lets get our script and plug-ins useable so we don't have to restart Maya
            if self.scripts_path not in sys.path:
                sys.path.append(self.scripts_path)
                print('Add scripts path [{}] to system paths'.format(self.scripts_path))
            else:
                print('scripts path in system paths')
                
                
            #Let's get our plug-in loaded!
            fromSource = os.path.join(self.package_install_path, 'fspy_plugin.py')
            toTarget = os.path.join(self.plugins_path, 'fspy_plugin.py')
            print('Copy From : {} to: {}'.format(fromSource, toTarget))
            plugin_copied = False
            try:
                shutil.copy(fromSource, toTarget)
                plugin_copied = True
            except Exception as e:
                print('copying plug-in failed')
               
            if plugin_copied:
                #Load Plugin And Autoload it
                if self.plugins_path not in os.environ['MAYA_PLUG_IN_PATH']:
                    print('plug-in dir:{0}'.format(self.plugins_path))
                    os.environ['MAYA_PLUG_IN_PATH'] += r';{0}'.format(self.plugins_path)
                
                try:
                    maya.cmds.loadPlugin('fspy_plugin')
                    maya.cmds.pluginInfo('fspy_plugin',  edit=True, autoload=True)
                except Exception as e:
                    print('FAILED to load plug-in:{0}'.format(e))
                
        else:
            #install failed so do alternative cleanup
            pass
        
        
        
    
def main():
    if MAYA_RUNNING:
        manager = Custom_Installer('fSpy_maya', 1.0, package_name = 'fspy-maya', include_site_packages = True)
        window_name =  'fSpy Maya'
        
        Resources.company_base64 = r'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'
        background_color = '#374146'
        logo_size = [64, 64]
        
        if not Resources.company_base64:    
            company_logo_file = r'C:\Users\natha\Documents\github\fSpy-Maya\resources\fspy_icon.png'
            
            company_string =  Resources.file_to_base64(company_logo_file)
            if company_string:
                print ("Use the next line for the Resources.company_base64")
                print(company_string)
                Resources.company_base64 = company_string

        global RESOURCES
        RESOURCES = Resources()        
        installer = Installer_UI(window_name, manager, background_color=background_color, company_logo_size=logo_size)
        RESOURCES.set_installer(installer)

        installer.show()


           
def onMayaDroppedPythonFile(*args):
    main()
    

def run():
    """
    Run is a function used by WingIDE to execute code after telling Maya to import the module
    """    
    main()
    

if __name__ == "__main__":
    main()
    
    

def __del__():
    print('deleting module')
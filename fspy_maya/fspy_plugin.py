
import maya.OpenMaya
import maya.OpenMayaUI
import maya.OpenMayaMPx

import pymel.core as pm

import fspy_maya

CAMERA_NAME = 'fspy_camera'
PLUGIN_NAME = 'fSpy Importer'

#https://help.autodesk.com/view/MAYAUL/2023/ENU/?guid=Maya_SDK_Writing_File_Translators_File_Translator_Examples_html
#https://download.autodesk.com/us/maya/2010help/API/class_m_fn_plugin.html#eb13e594951a71b750927ac44ddd4983
#https://download.autodesk.com/us/maya/2010help/API/class_m_px_file_translator.html
#C:\Program Files\Autodesk\Maya2023\devkit\devkitBase\devkit\plug-ins\python\api2
#mklink (use this to stick your github project into a module, so you can develop from two different locations)

class fSpy_Importer( maya.OpenMayaMPx.MPxFileTranslator ):
    def __init__(self):
        maya.OpenMayaMPx.MPxFileTranslator.__init__(self)    
    
    def defaultExtension(self, *args):
        return "fspy"
    
    def filter(self):
        return "*.fspy"    
    
    def haveNamespaceSupport(self, *args):
        return False
    
    def canBeOpened(self, *args):
        return False
    
    def haveReadMethod(self, *args):
        return True
    
    def reader(self, fileObject, option_string, mode):
        selection = pm.ls(sl=True, type='transform')
        
        #handle import if a camera is selected
        cameras = []
        for selected in selection:
            shape = selected.getShape()
            if shape and shape.type() == 'camera':
                cameras.append(selected)
         
        #we can't handle more than one camera in our selection       
        if len(cameras) > 1:
            error_message =  "Only 0-1 cameras can be selected when importing a file"
            pm.confirmDialog( title='fSpy Import Error', message=error_message, button=['Okay'] )
            pm.error(error_message)
        
        if not cameras:
            try:
                camera = pm.general.PyNode(CAMERA_NAME)
            except: 
                camera_shape = pm.createNode('camera')
                camera = camera_shape.getParent()
                pm.general.rename(camera, CAMERA_NAME)   
        else:
            camera = cameras[0]         
        
        
        file_name = fileObject.resolvedFullName()
        try:
            project =  fspy_maya.fspy.Project(file_name)
            fspy_maya.set_camera(project, camera)
        except Exception as e:
            sys.stderr.write( "Failed to read file information\n")
            pm.error(e)
            raise
    
    
# creator
def creator():
    return maya.OpenMayaMPx.asMPxPtr( fSpy_Importer() )

# initialize the script plug-in
def initializePlugin(mobject):
    plugin = maya.OpenMayaMPx.MFnPlugin(mobject, "Autodesk", "1.0", "Any")

    try:
        plugin.registerFileTranslator(PLUGIN_NAME, '', creator)
    except:
        sys.stderr.write("Failed to register node:{0}".format(PLUGIN_NAME))
        raise

# uninitialize the script plug-in
def uninitializePlugin( mobject ):
    plugin = maya.OpenMayaMPx.MFnPlugin( mobject )

    try:
        plugin.deregisterFileTranslator(PLUGIN_NAME)
    except:
        sys.stderr.write("Failed to unregister node:{0}".format(PLUGIN_NAME))
        raise
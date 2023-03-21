import math
import os
import imghdr
from struct import *

import pymel.core as pm

from fspy_maya import fspy


def set_camera(project, camera : pm.nodetypes.Transform):
    def _convert_rows(rows):
        x, y, z, =  rows[0], rows[1], rows[2]
        output = [
            [x[0], x[1], x[2], x[3]], 
            [z[0], z[1], z[2], z[3]], 
            [-y[0], -y[1], -y[2], -y[3]],
            [0, 0, 0, 1] 
        ]
        
        return output
    
    params = project.camera_parameters
    
    #set Rotation
    camera_matrix = pm.datatypes.Matrix(_convert_rows(params.camera_transfrom))
    camera.rotateOrder.set(0)
    camera.setTransformation(camera_matrix)
    camera.rotateOrder.set(3)
    camera.scale.set([100, 100, 100])
    
    #set translation
    x, y, z = params.camera_transfrom[0][3], params.camera_transfrom[2][3], params.camera_transfrom[1][3]    
    scale_length = 1

    unit =  project.reference_distance_unit
    if unit == 'Millimeters':
        scale_length = 0.1
    elif unit == 'Meters':
        scale_length = 100.0
    elif unit == 'Kilometers':
        scale_length = 100000.0
    elif unit == 'Inches':
        scale_length = 2.54 
    elif unit == 'Feet':
        scale_length = 30.48
    elif unit == 'Miles':
        scale_length = 160900.0
   
    camera.setTranslation(pm.datatypes.Vector(x * scale_length, y * scale_length, -z * scale_length))
    
    #set camera properties
    camera_shape : pm.nodetypes.Camera = camera.getShape()
    
    aspect_ratio = params.image_width / params.image_height 
    horizontal_aperture =  camera_shape.getHorizontalFilmAperture()
    camera_shape.setVerticalFilmAperture(horizontal_aperture / aspect_ratio)
    camera_shape.setHorizontalFieldOfView(math.degrees(params.fov_horiz))
    camera_shape.setVerticalFieldOfView(math.degrees(params.fov_vertical ))
    x_offset = -(camera_shape.getHorizontalFilmAperture() * params.principal_point[0]) / 2.0
    y_offset = -(camera_shape.getHorizontalFilmAperture() * params.principal_point[1]) / 2.0
    camera_shape.setHorizontalFilmOffset(x_offset)
    camera_shape.setVerticalFilmOffset(y_offset)
    
    #Adjust the image plane
    image_plane = pm.general.listConnections(camera_shape, type="imagePlane")
    image_plane_shape = None
    if image_plane:
        image_plane_shape = image_plane[0].getShape()
    else:
        #make a new image plane
        image_plane, image_plane_shape = pm.imagePlane(camera=camera)

    image_plane_shape.offset.set([x_offset, y_offset])
    image_path = image_plane_shape.imageName.get()
    
    if not image_path:
        tmp_dir =  pm.system.workspace.getPath()
        tmp_filename = "fspy-temp-image"
        image_path = os.path.join(tmp_dir, 'sourceimages', tmp_filename)
        
        #TODO: Find a better way to see the extension. Maybe project.image_data[1:4]?
        tmp_file = open(image_path, 'wb')
        tmp_file.write(project.image_data)
        tmp_file.close()
        ext = imghdr.what(image_path)
        
        if ext:
            os.remove(image_path)
            image_path = os.path.join(tmp_dir, 'sourceimages', '{0}.{1}'.format(tmp_filename, ext))
            tmp_file = open(image_path, 'wb')
            tmp_file.write(project.image_data)
            tmp_file.close()            
        
        image_plane_shape.imageName.set(image_path, type='string')


def run():
    fileFilter =  'fspy Files (*.fspy)'
    result = pm.fileDialog2(fileFilter=fileFilter, dialogStyle=1, fileMode=1)
    if result:
        selection = pm.ls(sl=True, type='transform')
        cameras = []
        for selected in selection:
            shape = selected.getShape()
            if shape and shape.type() == 'camera':
                cameras.append(selected)
                
        if len(cameras) > 1:
            pm.error("Only one camera can be selected.")
        
        if not cameras:
            camera_shape = pm.createNode('camera', n='fspy_camera')
            camera = camera_shape.getParent()
            
        else:
            camera = cameras[0]
        

        project_path = result[0]
        try:
            project =  fspy.Project(project_path)
        except Exception as e:
            print(e)
            return
        
        set_camera(project, camera)
    
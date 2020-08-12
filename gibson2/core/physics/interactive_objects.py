import pybullet as p
import os
import gibson2
import numpy as np
import random
import json

from gibson2.utils.assets_utils import get_model_path, get_texture_file, get_ig_scene_path, get_ig_model_path, get_ig_category_path
import xml.etree.ElementTree as ET
from gibson2.utils.utils import rotate_vector_3d

import logging


class Object(object):
    def __init__(self):
        self.body_id = None
        self.loaded = False

    def load(self):
        if self.loaded:
            return self.body_id
        self.body_id = self._load()
        self.loaded = True
        return self.body_id

    def get_position(self):
        pos, _ = p.getBasePositionAndOrientation(self.body_id)
        return pos

    def get_orientation(self):
        """Return object orientation
        :return: quaternion in xyzw
        """
        _, orn = p.getBasePositionAndOrientation(self.body_id)
        return orn

    def set_position(self, pos):
        _, old_orn = p.getBasePositionAndOrientation(self.body_id)
        p.resetBasePositionAndOrientation(self.body_id, pos, old_orn)

    def set_orientation(self, orn):
        old_pos, _ = p.getBasePositionAndOrientation(self.body_id)
        p.resetBasePositionAndOrientation(self.body_id, old_pos, orn)

    def set_position_orientation(self, pos, orn):
        p.resetBasePositionAndOrientation(self.body_id, pos, orn)


class YCBObject(Object):
    def __init__(self, name, scale=1):
        super(YCBObject, self).__init__()
        self.visual_filename = os.path.join(gibson2.assets_path, 'models', 'ycb', name,
                                            'textured_simple.obj')
        self.collision_filename = os.path.join(gibson2.assets_path, 'models', 'ycb', name,
                                               'textured_simple_vhacd.obj')
        self.scale = scale

    def _load(self):
        collision_id = p.createCollisionShape(p.GEOM_MESH,
                                              fileName=self.collision_filename,
                                              meshScale=self.scale)
        visual_id = p.createVisualShape(p.GEOM_MESH,
                                        fileName=self.visual_filename,
                                        meshScale=self.scale)

        body_id = p.createMultiBody(baseCollisionShapeIndex=collision_id,
                                    baseVisualShapeIndex=visual_id,
                                    basePosition=[0.2, 0.2, 1.5],
                                    baseMass=0.1)
        return body_id


class ShapeNetObject(Object):
    def __init__(self, path, scale=1., position=[0, 0, 0], orientation=[0, 0, 0]):
        super(ShapeNetObject, self).__init__()
        self.filename = path
        self.scale = scale
        self.position = position
        self.orientation = orientation

        self._default_mass = 3.
        self._default_transform = {
            'position': [0, 0, 0],
            'orientation_quat': [1. / np.sqrt(2), 0, 0, 1. / np.sqrt(2)],
        }
        pose = p.multiplyTransforms(positionA=self.position,
                                    orientationA=p.getQuaternionFromEuler(self.orientation),
                                    positionB=self._default_transform['position'],
                                    orientationB=self._default_transform['orientation_quat'])
        self.pose = {
            'position': pose[0],
            'orientation_quat': pose[1],
        }

    def _load(self):
        collision_id = p.createCollisionShape(p.GEOM_MESH,
                                              fileName=self.filename,
                                              meshScale=self.scale)
        body_id = p.createMultiBody(basePosition=self.pose['position'],
                                    baseOrientation=self.pose['orientation_quat'],
                                    baseMass=self._default_mass,
                                    baseCollisionShapeIndex=collision_id,
                                    baseVisualShapeIndex=-1)
        return body_id


class Pedestrian(Object):
    def __init__(self, style='standing', pos=[0, 0, 0]):
        super(Pedestrian, self).__init__()
        self.collision_filename = os.path.join(gibson2.assets_path, 'models', 'person_meshes',
                                               'person_{}'.format(style), 'meshes',
                                               'person_vhacd.obj')
        self.visual_filename = os.path.join(gibson2.assets_path, 'models', 'person_meshes',
                                            'person_{}'.format(style), 'meshes', 'person.obj')
        self.cid = None
        self.pos = pos

    def _load(self):
        collision_id = p.createCollisionShape(p.GEOM_MESH, fileName=self.collision_filename)
        visual_id = p.createVisualShape(p.GEOM_MESH, fileName=self.visual_filename)
        body_id = p.createMultiBody(basePosition=[0, 0, 0],
                                    baseMass=60,
                                    baseCollisionShapeIndex=collision_id,
                                    baseVisualShapeIndex=visual_id)
        p.resetBasePositionAndOrientation(body_id, self.pos, [-0.5, -0.5, -0.5, 0.5])
        self.cid = p.createConstraint(body_id,
                                      -1,
                                      -1,
                                      -1,
                                      p.JOINT_FIXED, [0, 0, 0], [0, 0, 0],
                                      self.pos,
                                      parentFrameOrientation=[-0.5, -0.5, -0.5, 0.5])  # facing x axis

        return body_id

    def reset_position_orientation(self, pos, orn):
        p.changeConstraint(self.cid, pos, orn)


class VisualMarker(Object):
    def __init__(self,
                 visual_shape=p.GEOM_SPHERE,
                 rgba_color=[1, 0, 0, 0.5],
                 radius=1.0,
                 half_extents=[1, 1, 1],
                 length=1,
                 initial_offset=[0, 0, 0]):
        """
        create a visual shape to show in pybullet and MeshRenderer

        :param visual_shape: pybullet.GEOM_BOX, pybullet.GEOM_CYLINDER, pybullet.GEOM_CAPSULE or pybullet.GEOM_SPHERE
        :param rgba_color: color
        :param radius: radius (for sphere)
        :param half_extents: parameters for pybullet.GEOM_BOX, pybullet.GEOM_CYLINDER or pybullet.GEOM_CAPSULE
        :param length: parameters for pybullet.GEOM_BOX, pybullet.GEOM_CYLINDER or pybullet.GEOM_CAPSULE
        :param initial_offset: visualFramePosition for the marker
        """
        super(VisualMarker, self).__init__()
        self.visual_shape = visual_shape
        self.rgba_color = rgba_color
        self.radius = radius
        self.half_extents = half_extents
        self.length = length
        self.initial_offset = initial_offset

    def _load(self):
        if self.visual_shape == p.GEOM_BOX:
            shape = p.createVisualShape(self.visual_shape,
                                        rgbaColor=self.rgba_color,
                                        halfExtents=self.half_extents,
                                        visualFramePosition=self.initial_offset)
        elif self.visual_shape in [p.GEOM_CYLINDER, p.GEOM_CAPSULE]:
            shape = p.createVisualShape(self.visual_shape,
                                        rgbaColor=self.rgba_color,
                                        radius=self.radius,
                                        length=self.length,
                                        visualFramePosition=self.initial_offset)
        else:
            shape = p.createVisualShape(self.visual_shape,
                                        rgbaColor=self.rgba_color,
                                        radius=self.radius,
                                        visualFramePosition=self.initial_offset)
        body_id = p.createMultiBody(baseVisualShapeIndex=shape, baseCollisionShapeIndex=-1)

        return body_id

    def set_color(self, color):
        p.changeVisualShape(self.body_id, -1, rgbaColor=color)


class BoxShape(Object):
    def __init__(self, pos=[1, 2, 3], dim=[1, 2, 3], visual_only=False, mass=1000, color=[1, 1, 1, 1]):
        super(BoxShape, self).__init__()
        self.basePos = pos
        self.dimension = dim
        self.visual_only = visual_only
        self.mass = mass
        self.color = color

    def _load(self):
        baseOrientation = [0, 0, 0, 1]
        colBoxId = p.createCollisionShape(p.GEOM_BOX, halfExtents=self.dimension)
        visualShapeId = p.createVisualShape(p.GEOM_BOX, halfExtents=self.dimension, rgbaColor=self.color)
        if self.visual_only:
            body_id = p.createMultiBody(baseCollisionShapeIndex=-1,
                                        baseVisualShapeIndex=visualShapeId)
        else:
            body_id = p.createMultiBody(baseMass=self.mass,
                                        baseCollisionShapeIndex=colBoxId,
                                        baseVisualShapeIndex=visualShapeId)

        p.resetBasePositionAndOrientation(body_id, self.basePos, baseOrientation)

        return body_id


class InteractiveObj2(Object):
    """
    Interactive Objects are represented as a urdf, but doesn't have motors
    """

    def __init__(self, xml_element):
        super(InteractiveObj2, self).__init__()

        category = xml_element.attrib["category"]
        model = xml_element.attrib['model']
        model_path = ""
                
        if category == "building":
            model_path = get_ig_scene_path(model)
            filename = model_path + "/" + model + "_building.urdf"
        else:
            category_path = get_ig_category_path(category)
            if model == 'random':
                assert len(os.listdir(category_path)) != 0, "There are no models in category folder {}".format(category_path)
                model = random.choice(os.listdir(category_path))
            else:
                model = xml_element.attrib['model']

            model_path = get_ig_model_path(category, model)
            filename = model_path + "/" + model + ".urdf"            
 
        self.filename = filename

        logging.info("Loading " + filename)

        self.object_tree = ET.parse(filename)


        # Change the mesh filenames to include the entire path
        for mesh in self.object_tree.iter("mesh"):
            mesh.attrib['filename'] = model_path + "/" + mesh.attrib['filename']

        # Apply the bounding box size
        # We need to scale 1) the meshes, 2) the position of meshes, 3) the position of joints, 4) the orientation axis of joints
        # The problem is that those quantities are given wrt. its parent link frame, and this can be rotated wrt. the frame the scale was given in
        # Solution: parse the kin tree joint by joint, extract the rotation, rotate the scale, apply rotated scale to 1, 2, 3, 4 in the child link frame
        if "bounding_box" in xml_element.keys():
            bounding_box = np.array([float(val) for val in xml_element.attrib["bounding_box"].split(" ")])
            logging.debug(bounding_box)
            with open(model_path + '/misc/bbox.json', 'r') as bbox_file:
                data = json.load(bbox_file)
                bbox_max = np.array(data['max'])
                bbox_min = np.array(data['min'])
                original_bbox = bbox_max - bbox_min
            scale = np.divide(bounding_box, original_bbox) 
            logging.debug(scale)

            parent_link_name = "base_link"
            while parent_link_name != None:
                parent_link = [link for link in self.object_tree.findall("link") if link.attrib["name"] == parent_link_name][0]

                for xml_child in parent_link.iter():
                    #Apply the scale to all elements: meshes, joint parameters
                    for mesh in xml_child.iter("mesh"):
                        if "scale" in mesh.keys():
                            current_scale = np.array([float(val) for val in mesh.attrib["scale"].split(" ")])
                            new_scale = np.multiply(current_scale, scale)
                            mesh.attrib['scale'] = ' '.join(map(str, new_scale))

                        else:
                            mesh.set('scale',' '.join(map(str, scale)))

                    for origin in xml_child.iter("origin"):
                        current_origin_xyz = np.array([float(val) for val in origin.attrib["xyz"].split(" ")])
                        new_origin_xyz = np.multiply(current_origin_xyz, scale)
                        origin.attrib['xyz'] = ' '.join(map(str, new_origin_xyz))
                        #print("New origin xyz {}",new_origin_xyz)

                logging.debug(parent_link.attrib["name"])

                joint_news = [joint for joint in self.object_tree.findall("joint") if joint.find("parent").attrib["link"] == parent_link.attrib["name"]]
                if len(joint_news) != 0:

                    for joint_new in joint_news:

                        # The location of the joint frames are scaled in the direction of the parent (current scale)
                        for origin in joint_new.iter("origin"):
                            current_origin_xyz = np.array([float(val) for val in origin.attrib["xyz"].split(" ")])
                            new_origin_xyz = np.multiply(current_origin_xyz, scale)
                            origin.attrib['xyz'] = ' '.join(map(str, new_origin_xyz))

                        # Get the rotation of the joint frame and apply it to the scale
                        if "rpy" in joint_new.keys():
                            joint_frame_rot = np.array([float(val) for val in joint_new.attrib['rpy'].split(" ")])
                            # Rotate the scale
                            scale = rotate_vector_3d(scale, *joint_frame_rot, cck=True)
                            scale = np.absolute(scale)

                        # The axis of the joint is defined in the joint frame, we scale it after applying the rotation
                        for axis in self.object_tree.iter("axis"):
                            current_axis_xyz = np.array([float(val) for val in axis.attrib["xyz"].split(" ")])
                            new_axis_xyz = np.multiply(current_axis_xyz, scale)
                            new_axis_xyz /= np.linalg.norm(new_axis_xyz)
                            axis.attrib['xyz'] = ' '.join(map(str, new_axis_xyz))
                            #print("New axis xyz {}",new_axis_xyz)

                        # Update the parent_link_name to the child in this joint
                        parent_link_name = joint_news[0].find("child").attrib["link"]
                else:
                    parent_link_name = None

    def _load(self):
        body_id = p.loadURDF(self.filename, 
                             flags=p.URDF_USE_MATERIAL_COLORS_FROM_MTL)
        self.mass = p.getDynamicsInfo(body_id, -1)[0]

        return body_id

class InteractiveObj(Object):
    """
    Interactive Objects are represented as a urdf, but doesn't have motors
    """

    def __init__(self, filename, scale=1):
        super(InteractiveObj, self).__init__()
        self.filename = filename
        self.scale = scale

    def _load(self):
        body_id = p.loadURDF(self.filename, globalScaling=self.scale,
                             flags=p.URDF_USE_MATERIAL_COLORS_FROM_MTL)
        self.mass = p.getDynamicsInfo(body_id, -1)[0]

        return body_id


class SoftObject(Object):
    def __init__(self, filename, basePosition=[0, 0, 0], baseOrientation=[0, 0, 0, 1], scale=-1, mass=-1,
                 collisionMargin=-1, useMassSpring=0, useBendingSprings=0, useNeoHookean=0, springElasticStiffness=1,
                 springDampingStiffness=0.1, springBendingStiffness=0.1, NeoHookeanMu=1, NeoHookeanLambda=1,
                 NeoHookeanDamping=0.1, frictionCoeff=0, useFaceContact=0, useSelfCollision=0):
        super(SoftObject, self).__init__()
        self.filename = filename
        self.scale = scale
        self.basePosition = basePosition
        self.baseOrientation = baseOrientation
        self.mass = mass
        self.collisionMargin = collisionMargin
        self.useMassSpring = useMassSpring
        self.useBendingSprings = useBendingSprings
        self.useNeoHookean = useNeoHookean
        self.springElasticStiffness = springElasticStiffness
        self.springDampingStiffness = springDampingStiffness
        self.springBendingStiffness = springBendingStiffness
        self.NeoHookeanMu = NeoHookeanMu
        self.NeoHookeanLambda = NeoHookeanLambda
        self.NeoHookeanDamping = NeoHookeanDamping
        self.frictionCoeff = frictionCoeff
        self.useFaceContact = useFaceContact
        self.useSelfCollision = useSelfCollision

    def _load(self):
        body_id = p.loadSoftBody(self.filename, scale=self.scale, basePosition=self.basePosition,
                                 baseOrientation=self.baseOrientation, mass=self.mass,
                                 collisionMargin=self.collisionMargin, useMassSpring=self.useMassSpring,
                                 useBendingSprings=self.useBendingSprings, useNeoHookean=self.useNeoHookean,
                                 springElasticStiffness=self.springElasticStiffness,
                                 springDampingStiffness=self.springDampingStiffness,
                                 springBendingStiffness=self.springBendingStiffness,
                                 NeoHookeanMu=self.NeoHookeanMu, NeoHookeanLambda=self.NeoHookeanLambda,
                                 NeoHookeanDamping=self.NeoHookeanDamping, frictionCoeff=self.frictionCoeff,
                                 useFaceContact=self.useFaceContact, useSelfCollision=self.useSelfCollision)

        # Set signed distance function voxel size (integrate to Simulator class?)
        p.setPhysicsEngineParameter(sparseSdfVoxelSize=0.1)

        return body_id

    def addAnchor(self, nodeIndex=-1, bodyUniqueId=-1, linkIndex=-1, bodyFramePosition=[0, 0, 0], physicsClientId=0):
        p.createSoftBodyAnchor(self.body_id, nodeIndex, bodyUniqueId, linkIndex, bodyFramePosition, physicsClientId)


class RBOObject(InteractiveObj):
    def __init__(self, name, scale=1):
        filename = os.path.join(gibson2.assets_path, 'models', 'rbo', name, 'configuration',
                                '{}.urdf'.format(name))
        super(RBOObject, self).__init__(filename, scale)

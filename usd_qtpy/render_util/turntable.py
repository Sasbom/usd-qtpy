# Turn table utilities.

from typing import Union
import os
from contextlib import ExitStack

from pxr import Usd, UsdGeom, Sdf, Gf

from . import framing_camera, playblast
from .base import (RenderReportable, 
                   TempStageOpen,
                   defer_file_deletion,
                   get_tempfolder, 
                   using_tempfolder)


def create_turntable_xform(stage: Usd.Stage,
                           path: Union[Sdf.Path, str],
                           name: str = "turntableXform",
                           length: int = 100, 
                           frame_start: int = 0, 
                           repeats: int = 1,
                           bounds: Gf.Range3d = None) -> UsdGeom.Xform:
    """
    Creates a turntable Xform that contains animation spinning around the up axis, in the center floor of the stage.
    We repeat the entire duration when repeats are given as an arguement.
    A length of 100 with 3 repeats will result in a 300 frame long sequence
    """
    from pxr.UsdGeom import XformOp
    
    if isinstance(path, str):
        path = Sdf.Path(path)
    
    path = path.AppendPath(name)

    is_z_up = framing_camera.get_stage_up(stage) == "Z"
    
    if bounds is None:
        bounds = framing_camera.get_stage_boundingbox(stage)
    centroid = bounds.GetMidpoint()

    xform = UsdGeom.Xform.Define(stage, path)

    if is_z_up:
        translate = Gf.Vec3d(centroid[0], centroid[1], 0) # Z axis = floor normal
    else:
        translate = Gf.Vec3d(centroid[0], 0, centroid[2]) # Y axis = floor normal

    # Move to centroid of bounds, rotate, move back to origin
    xform.AddTranslateOp(XformOp.PrecisionDouble, "rotPivot").Set(translate)
    add_turntable_spin_op(xform, length, frame_start, repeats, is_z_up)
    xform.AddTranslateOp(XformOp.PrecisionDouble, "rotPivot", isInverseOp=True)
    
    return xform


def create_turntable_camera(stage: Usd.Stage,
                            root: Union[Sdf.Path, str] = Sdf.Path("/"),
                            name: str = "turntableCam",
                            fit: float = 1.1,
                            width: int = 16,
                            height: int = 9,
                            length: int = 100,
                            frame_start: int = 0) -> UsdGeom.Camera:
    """
    Creates a complete setup with a stage framing perspective camera, within an animated, rotating Xform.
    """
    if isinstance(root, str):
        root = Sdf.Path(root)

    xform = create_turntable_xform(
        stage, root, length=length, frame_start=frame_start
    )
    xform_path = xform.GetPath()

    cam = framing_camera.create_framing_camera_in_stage(
        stage, xform_path, name, fit, width, height)

    return cam


def add_turntable_spin_op(xformable: UsdGeom.Xformable,
                          length: int = 100,
                          frame_start: int = 0,
                          repeats: int = 1,
                          is_z_up: bool = False) -> UsdGeom.XformOp:
    """Add Rotate XformOp with 360 degrees turntable rotation keys to prim"""
    from pxr.UsdGeom import XformOp
    # TODO: Maybe check for existing operations before blatantly adding one.
    if is_z_up:
        spin_op = xformable.AddRotateZOp(XformOp.PrecisionDouble)
    else:
        spin_op = xformable.AddRotateYOp(XformOp.PrecisionDouble)

    spin_op.Set(time=frame_start, value=0)

    # Avoid having the last frame the same as the first frame so the cycle
    # works out nicely over the full length. As such, we remove one step
    frame_end = frame_start + (length * repeats) - 1
    step_per_frame = 360 / length
    spin_op.Set(time=frame_end, value=(repeats * 360) - step_per_frame)

    return spin_op


def get_turntable_frames_string(length: int = 100,
                                frame_start: int = 0,
                                repeats: int = 1) -> str:
    """
    Get a usable string argument for frames from turntable time params.
    """
    frame_end = frame_start + (length * repeats) - 1
    return playblast.get_frames_string(frame_start,frame_end,1)


@using_tempfolder
def turntable_from_file(stage: Usd.Stage,
                        turntable_filename: str = R"./assets/turntable/turntable_preset.usda",
                        export_path: str = R"./temp/render",
                        renderer: str = "GL",
                        length: int = 100,
                        frame_start: int = 1,
                        repeats: int = 1,
                        width: int = 16,
                        height: int = 9,
                        camera_path : Union[str, Sdf.Path] = None,
                        qt_report_instance: RenderReportable = None):
    """
    Generates a turntable from a preset USD file, not unlike Prism.
    
    The turntable must have the following structure:
    - /turntable <- default primitive Xform
    - /turntable/parent <- Xform that rotates
    - a camera somewhere under /turntable/
    
    Optional:
    - /turntable/bounds/bound_box <- a geometry primitive 
                                     that scales input to fit itself.
    """

    # TODO: Infer frame range from turntable stage.

    # collect info about subject
    subject_zup = framing_camera.get_stage_up(stage) == "Z"

    # get tempfolder
    tempfolder = get_tempfolder()

    # export subject
    # turntable_filename = R"./assets/turntable_preset.usd"
    subject_filename = R"subject.usda"
    subject_filename = os.path.join(tempfolder,subject_filename)
    subject_filename = os.path.abspath(subject_filename)


    stage.Export(subject_filename)

    # create scene in memory
    ttable_stage = Usd.Stage.CreateInMemory()

    turntable_ref = ttable_stage.OverridePrim("/turntable_reference")
    turntable_ref.GetReferences().AddReference(turntable_filename)

    # conform turntable to Y up
    turntable_zup = file_is_zup(turntable_filename)

    if turntable_zup:
        turntable_ref_xformable = UsdGeom.Xformable(turntable_ref)
        turntable_ref_xformable.AddRotateXOp().Set(-90)

    # check if required prims are actually there
    turntable_parent_prim = ttable_stage.GetPrimAtPath("/turntable_reference/parent")
    
    turntable_camera = next(playblast.iter_stage_cameras(ttable_stage), None)

    if camera_path is not None:
        if isinstance(camera_path, Sdf.Path):
            camera_path = camera_path.pathString

        # Reroute root (say that 10 times)
        camera_path.replace("turntable","turntable_reference")
        camera_path = Sdf.Path(camera_path)    
        
        camera_prim = ttable_stage.GetPrimAtPath(camera_path)
        if camera_prim.IsValid():
            turntable_camera = UsdGeom.Camera(camera_prim)
        else:
            raise RuntimeError(f"Turntable Camera at "
                               f"{camera_path.pathString} is missing.")
        

    # Validate
    missing = []
    if not turntable_parent_prim.IsValid():
        missing.append("Missing: /turntable/parent")
    if turntable_camera is None:
        missing.append("Missing: Usd Camera")
    if missing:
        raise RuntimeError(
            "Turntable file doesn't have all necessary components."
            "\n" + "\n".join(missing)
        )

    # Create a reference within the parent of the new turntable stage
    # References do need xformables created.
    ref_adress ="/turntable_reference/parent/subject_reference"
    subject_ref = ttable_stage.OverridePrim(ref_adress)
    subject_ref.GetReferences().AddReference(subject_filename)
    subject_prim = ttable_stage.GetPrimAtPath("/turntable_reference/parent")

    subject_ref_xformable = UsdGeom.Xformable(subject_ref)

    if subject_zup:
        subject_ref_xformable.AddRotateXOp().Set(-90)

    # get bbox of subject and center stage
    timecode = 0
    bbox_cache = UsdGeom.BBoxCache(timecode, ["default"])
    subject_nofit_bbox = bbox_cache.ComputeWorldBound(subject_prim).GetBox()
    
    subject_nofit_size = subject_nofit_bbox.GetSize()

    # Get goal geometry boundingbox if it exists, and fit primitive to it
    
    bbox_prim = ttable_stage.GetPrimAtPath("/turntable_reference/bounds")

    if bbox_prim.IsValid():
        goal_bbox = bbox_cache.ComputeWorldBound(bbox_prim).GetBox()
        goal_size = goal_bbox.GetSize()
        min_sizediff = goal_size[0] / subject_nofit_size[0]
        for index in range(1, 3):
            min_sizediff = min(goal_size[index] / subject_nofit_size[index],
                               min_sizediff)

        # SCALE
        subject_ref_xformable.AddScaleOp(UsdGeom.XformOp.PrecisionDouble)\
                             .Set(Gf.Vec3d(min_sizediff))
    else:
        min_sizediff = 1

    subject_prim = ttable_stage.GetPrimAtPath("/turntable_reference/parent")
    
    # clear bboxcache
    bbox_cache.Clear()

    # get bbox of subject and center stage
    subject_bbox = bbox_cache.ComputeWorldBound(subject_prim).GetBox()
    subject_bounds_min = subject_bbox.GetMin()
    subject_centroid = subject_bbox.GetMidpoint()

    # center geometry.
    if subject_zup:
        subject_center_translate = Gf.Vec3d(
                                            -subject_centroid[0] / min_sizediff,
                                            subject_centroid[2] / min_sizediff,
                                            -subject_bounds_min[1] / min_sizediff
                                            )
    else:
        subject_center_translate = Gf.Vec3d(
                                            -subject_centroid[0] / min_sizediff,
                                            -subject_bounds_min[1] / min_sizediff,
                                            -subject_centroid[2] / min_sizediff
                                            ) 
    
    subject_ref_xformable.AddTranslateOp(
                          UsdGeom.XformOp.PrecisionDouble,"center_centroid")\
                         .Set(subject_center_translate)
    
    # turn off the lights if GL
    if renderer == "GL":
        lights_prim = ttable_stage.GetPrimAtPath("/turntable_reference/scene/lights")
        if lights_prim.IsValid():
            lights_prim.GetAttribute("visibility").Set("invisible",0)

    realstage_filename = R"turntable_assembly.usd"
    realstage_filename = os.path.join(tempfolder, realstage_filename)
    realstage_filename = os.path.abspath(realstage_filename)

    ttable_stage.Export(realstage_filename)

    # frame range 1-100 in standard file
    # get_file_timerange_as_string should be preferred, but it doesn't work atm.
    frames_string = get_turntable_frames_string(length,frame_start,repeats)
    render_path = os.path.abspath(export_path)

    print("Rendering",frames_string,render_path)

    # create an exit stack that will neatly clean up all the things in order.
    with ExitStack() as stack:
        # enter stage context, and also enter context for deferring
        # subject file to be deleted.
        realstage = stack.enter_context(TempStageOpen(realstage_filename, True))
        stack.enter_context(defer_file_deletion(subject_filename))

        turntable_camera = next(playblast.iter_stage_cameras(realstage),None)
        turntable_camera = UsdGeom.Camera(turntable_camera)
        turntable_camera = framing_camera.camera_conform_sensor_to_aspect(
            turntable_camera,
            width,
            height
        )

        playblast.render_playblast(realstage,
                                   render_path,
                                   frames=frames_string,
                                   width=width,
                                   camera=turntable_camera,
                                   renderer=renderer,
                                   qt_report_instance=qt_report_instance)
        # remove reference count of realstage within this scope.
        # This is essential to let garbage collection take place.
        del realstage


def file_is_zup(path: str) -> bool:
    stage = Usd.Stage.CreateInMemory(path)
    return framing_camera.get_stage_up(stage) == "Z"


def get_file_timerange_as_string(path: str) -> str:
    """
    Attempt to get timerange from a USD file.
    """
    start = 0
    end = 100

    with TempStageOpen(path) as stage:

        if stage.HasAuthoredTimeCodeRange():
            start = int(stage.GetStartTimeCode())
            end = int(stage.GetEndTimeCode())
        else:
            print("No Timecode found")

    return playblast.get_frames_string(start,end)

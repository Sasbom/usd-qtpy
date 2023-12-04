# Playblast framework
# Inspired by: Prism, usdrecord

# NOTES:
# pxr.UsdViewq.ExportFreeCameraToStage will export the camera from the view (a FreeCamera/ pxr.Gf.Camera, purely OpenGL)
import logging
import sys
from typing import Union
from collections.abc import Generator

from qtpy import QtCore
from pxr import Usd, UsdGeom
from pxr import UsdAppUtils
from pxr import Tf, Sdf
from pxr.Usdviewq.stageView import StageView

from ..viewer import CustomStageView # Wrapper around Usdviewq's StageView

from . import framing_camera

def _setup_opengl_widget(width: int, height: int, samples: int = 4):
    """
    Utility function to produce a Qt openGL widget capable of catching
    the output of a render
    """

    from qtpy import QtOpenGL

    # format object contains information about the Qt OpenGL buffer.
    QGLformat = QtOpenGL.QGLFormat()
    QGLformat.setSampleBuffers(True) # Enable multisample buffer
    QGLformat.setSamples(samples) # default samples is 4 / px

    GLWidget = QtOpenGL.QGLWidget(QGLformat)
    GLWidget.setFixedSize(QtCore.QSize(width,height))

    GLWidget.makeCurrent() # bind widget buffer as target for OpenGL operations.

    return GLWidget

def iter_stage_cameras(stage: Usd.Stage, TraverseAll = True) -> Generator[UsdGeom.Camera]:
    """
    Return a generator of all camera primitives.
    TraverseAll is on by default. This means that inactive cameras will also be shown.
    """
    # Ref on differences between traversal functions: https://openusd.org/dev/api/class_usd_stage.html#adba675b55f41cc1b305bed414fc4f178 

    if TraverseAll:
        gen = stage.TraverseAll()
    else: 
        gen = stage.Traverse()
    
    for prim in gen:
        if prim.IsA(UsdGeom.Camera):
            yield prim

def camera_from_stageview(stage: Usd.Stage, stageview: Union[StageView, CustomStageView], name: str = "playblastCam") -> UsdGeom.Camera:
    """ Catches a stage view whether it'd be from the custom viewer or from the baseclass and calls the export to stage function."""
    stageview.ExportFreeCameraToStage(stage,name)
    return UsdGeom.Camera.Get(stage,Sdf.Path(f"/{name}"))

# Source: UsdAppUtils.colorArgs.py
def get_color_args():
    return ("disabled","sRGB","openColorIO")

def get_complexity_levels() -> Generator[str]:
    """
    Returns a generator that iterates through all registered complexity presets in UsdAppUtils.complexityArgs
    """
    from pxr.UsdAppUtils.complexityArgs import RefinementComplexities as Complex
    return (item.name for item in Complex._ordered)

def iter_renderplugin_names() -> Generator[str]:
    """
    Returns a generator that will iterate through all names of Render Engine Plugin / Hydra Delegates
    """
    from pxr.UsdImagingGL import Engine as En
    return (En.GetRendererDisplayName(pluginId) for pluginId in En.GetRendererPlugins())

def get_renderplugin(enginestr: str):
    from pxr.UsdImagingGL import Engine as En
    for plug in En.GetRendererPlugins():
        if enginestr == En.GetRendererDisplayName(plug):
            return plug
    return None

def check_renderplugin_name(enginestr: str) -> Union[str, None]:
    plugnames = iter_renderplugin_names()
    if enginestr in plugnames:
        return enginestr
    return None

def get_frames_string(start_time: int, end_time: int = None, frame_stride: float = None) -> str:
    """
    Takes a set of numbers and structures it so that it can be passed as frame string argument to e.g. render_playblast
    Given only a start time, it'll render a frame at that frame.
    Given a start and end time, it'll render a range from start to end, including end. (0-100 = 101 frames)
    Given a start, end, and stride argument, it'll render a range with a different frame interval. 
    (rendering every other frame can be done by setting this to 2.)
    Output for 1, 2 and 3 arguments respectively: 
    'start_time', 'start_time:end_time', 'start_time:end_timexframe_stride'
    as defined by the USD standard.
    """
    # Keep adhering to USD standard as internally defined.
    from pxr.UsdUtils import TimeCodeRange
    range_token = TimeCodeRange.Tokens.RangeSeparator    # ":"
    stride_token = TimeCodeRange.Tokens.StrideSeparator  # "x"

    collect_str = f"{start_time}" # single frame
    if end_time is not None:
        collect_str += f"{range_token}{end_time}" # range of frames
        if frame_stride is not None:
            collect_str += f"{stride_token}{frame_stride}" # range of frames + stride
    
    return collect_str

def tuples_to_frames_string(time_tuples: list[Union[tuple[int], tuple[int, int], tuple[int, int, float]]]) -> str:
    """
    Convert an iterable (e.g. list/generator) of tuples containing structured frame data:
    tuple(start_time, end_time, frame_stride), same as the arguments to get_frames_string,
    to a single string that can be parsed as a frames_string argument for multiple frames.
    example input: (1,) , (1 , 50, 0.5), (8,10)
    example output: '1,1:50x0.5,8:10'
    (according to standards defined for UsdAppUtils.FrameRecorder)
    """
    # keep adhering to USD standard as internally defined.
    from pxr.UsdAppUtils.framesArgs import FrameSpecIterator
    separator_token = FrameSpecIterator.FRAMESPEC_SEPARATOR # ","

    def tuple_gen(tuple_iterable):
        it = iter(tuple_iterable)
        val = next(it,None)
        while val:
            if len(val) <= 3:
               yield get_frames_string(*val) 
            
            val = next(it,None)
    
    return separator_token.join(tuple_gen(time_tuples))

def render_playblast(stage: Usd.Stage, outputpath: str, frames: str, width: int, 
                    camera: UsdGeom.Camera = None, complexity: Union[str,int] = "High",
                    renderer: str = None, colormode: str = "sRGB"): 
    from pxr.UsdAppUtils.framesArgs import FrameSpecIterator, ConvertFramePlaceholderToFloatSpec
    from pxr.UsdAppUtils.complexityArgs import RefinementComplexities as Complex
    from pxr import UsdUtils

    # rectify pathname for use in .format with path.format(frame = timeCode.getValue())
    if not (outputpath := ConvertFramePlaceholderToFloatSpec(outputpath)):
        raise ValueError("Invalid/Empty filepath for rendering")

    # ensure right complexity object is picked.
    # the internal _RefinementComplexity.value is used to set rendering quality
    if isinstance(complexity,str):
        # ensure key correctness
        complexity = complexity.lower() # set all to lowercase
        complexity = complexity.title() # Uppercase Each Word (In Case Of "Very High")
        preset_names = get_complexity_levels()
        if complexity not in preset_names:
            raise ValueError(f"Value: {complexity} entered for complexity is not valid")
        
        complex_level = Complex.fromName(complexity)
    elif isinstance(complexity,int):
        complexity = min(max(complexity,0),3) # clamp to range of 0-3, 4 elements
        complex_level = Complex._ordered[complexity]

    complex_level = complex_level.value

    # deduce default renderer based on platform if not specified.
    if renderer is None:
        if (os := sys.platform) == "nt" or os == "win32":
            renderer = "GL"
        elif os == "darwin":
            renderer = "Metal"
        else:
            renderer = "GL"

    # validate render engine
    if not check_renderplugin_name(renderer):
        raise ValueError("Render plugin arguement invalid")
    renderer = get_renderplugin(renderer)

    # No Camera: Assume scene wide camera (same behavior as usdrecord)
    if not camera:
        # Same procedure as default for pxr.UsdAppUtils.cameraArgs.py
        print("No cam specified, using PrimaryCamera")
        path = Sdf.Path(UsdUtils.GetPrimaryCameraName())
        camera = UsdAppUtils.GetCameraAtPath(stage, path)

    if colormode not in get_color_args():
        raise ValueError("Color correction mode specifier is invalid.")

    # Set up OpenGL FBO to write to within Widget
    # Actual size doesn't matter
    # it does need to be stored in a variable though, otherwise it'll be collected
    ogl_widget = _setup_opengl_widget(width,width) 

    # Create FrameRecorder
    frame_recorder = UsdAppUtils.FrameRecorder()
    frame_recorder.SetRendererPlugin(renderer)
    frame_recorder.SetImageWidth(width) # Only width is needed, heigh will be computer from camera properties.
    frame_recorder.SetComplexity(complex_level)
    frame_recorder.SetColorCorrectionMode(colormode)
    #frameRecorder.SetIncludedPurposes(["default","render","proxy","guide"]) # set to all purposes for now.

    # Use Usds own frame specification parser
    # The following are examples of valid FrameSpecs:
    # 123 - 101:105 - 105:101 - 101:109x2 - 101:110x2 - 101:104x0.5
    frame_iterator = FrameSpecIterator(frames)

    if not frame_iterator:
        frame_iterator = [Usd.TimeCode.EarliestTime()]

    for time_code in frame_iterator:
        current_frame = outputpath.format(frame = time_code.GetValue())
        try:
            frame_recorder.Record(stage, camera, time_code, current_frame)
        except Tf.ErrorException as e:
            logging.error("Recording aborted due to the following failure at time code %s: %s",time_code, e)
            break
    
    # Set reference to None so that it can be collected before Qt context.
    frame_recorder = None
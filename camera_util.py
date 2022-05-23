import requests
from requests.auth import HTTPBasicAuth  
import cv2
import time

def get_camera_img_url(camera_hostname):
    return 'http://'+camera_hostname+'/img/snapshot.cgi?size=4'

def isConnected(camera_hostname):
    url=get_camera_img_url(camera_hostname)
    cap=cv2.VideoCapture(url)
    return cap is not None and cap.isOpened()

'''
Queries camera's infrared filter
Returns:
tuple (ok, filter): ok: request status, filter: filter value (0 - filter is off, 1 - filter is on)
'''
def isInfraredOn(camera_hostname):
    URL='http://'+camera_hostname+'/io/query_filter.cgi'
    r = requests.get(url = URL, auth=HTTPBasicAuth('administrator', ''))
    return (r.ok, r.text[-3])
 
def get_camera_video_url(camera_hostname):
    return 'rtsp://'+camera_hostname+'/img/video.sav'

def change_camera_settings(hostname, group, property, value):
    URL = 'http://'+hostname+'/adm/set_group.cgi'
    PARAMS = {'group': group , property: value}        
    # sending get request and saving the response as response object
    r = requests.get(url = URL, params = PARAMS,auth=HTTPBasicAuth('administrator', ''))
    return r.ok

def reset_to_default(camera_hostname):
    URL='http://'+camera_hostname+'/adm/reset_to_default.cgi'
    r=requests.get(url=URL,auth=HTTPBasicAuth('administrator', ''))

'''
Shots a central part of fov
Args:
camera_hostname: camera IP address 
crop_width: width of a central part of fov
crop_height: height of a central part of fov
Returns:
frame of size (crop_height, crop_width, 3)
'''
def shoot(camera_hostname, crop_width, crop_height):
    url=get_camera_img_url(camera_hostname)
    cap=cv2.VideoCapture(url)
    if cap is None or not cap.isOpened():
        return None
    ret, frame = cap.read()        
    width=int(cap.get(3))
    height=int(cap.get(4))
    w_offset=(width-crop_width)//2
    h_offset=(height-crop_height)//2
    return frame[h_offset:(h_offset+crop_height),w_offset:(w_offset+crop_width)]

'''
Films LED under certain time
Args:
camera_hostname: camera IP address 
crop_width: width of a central part of fov
crop_height: height of a central part of fov
y_UL: y coordinate of upper left corner of the LED on the central part of fov ((0,0) - upper left corner of the central part of the image)
x_UL: x coordinate of upper left corner of the LED on the central part of fov ((0,0) - upper left corner of the central part of the image) 
y_BR: y coordinate of bottom right corner of the LED on the central part of fov ((0,0) - upper left corner of the central part of the image)
x_BR: x coordinate of bottom right corner of the LED on the central part of fov ((0,0) - upper left corner of the central part of the image)
time_span: time in seconds, for which video should be taken
Returns:
list of frames of size (y_BR - y_UL, x_BR-x_UL, 3) that were provided by the camera during time_span seconds
'''
def video (camera_hostname, crop_width, crop_height, y_UL, x_UL, y_BR, x_BR, time_span):
    url=get_camera_video_url(camera_hostname)
    cap=cv2.VideoCapture(url)
    if cap is None or not cap.isOpened():
        return None
    frames=[]
    t=time.time()
    while(cap.isOpened() and time.time()-t < time_span):
        ret,frame=cap.read()
        if ret==True:
            width=int(cap.get(3))
            height=int(cap.get(4))
            w_offset=(width-crop_width)//2
            h_offset=(height-crop_height)//2        
            frame=frame[h_offset:(h_offset+crop_height),w_offset:(w_offset+crop_width)]                        
            frames.append(frame[y_UL:y_BR, x_UL:x_BR])
    return frames

def switch_to_day_mode(camera_hostname):
    return change_camera_settings(camera_hostname,'VIDEO','dn_sch', 2)

def switch_to_auto_mode(camera_hostname):
    return change_camera_settings(camera_hostname,'VIDEO','dn_sch', 1) #3-night. 1- auto

def switch_to_high_video_quality(camera_hostname):
    return change_camera_settings(camera_hostname,'H264','quality_level', 5)

def switch_GOV_length(camera_hostname):
    return change_camera_settings(camera_hostname,'H264','gov_length', 150)

def switch_to_default_video_quality(camera_hostname):
    return change_camera_settings(camera_hostname,'H264','quality_level', 3)
    
def switch_to_high_resolution(camera_hostname):
    return change_camera_settings(camera_hostname,'H264','resolution', 4)

def switch_to_high_profile(camera_hostname):
    return change_camera_settings(camera_hostname,'H264','profile', 100)

def switch_to_high_saturation(camera_hostname):
    return change_camera_settings(camera_hostname,'VIDEO','saturation', 7) #4 - default

def switch_to_high_exposure(camera_hostname):
    return change_camera_settings(camera_hostname, 'VIDEO','exposure',7)
    
def switch_to_low_exposure(camera_hostname):
    return change_camera_settings(camera_hostname, 'VIDEO','exposure',1)
        
def switch_to_default_saturation(camera_hostname):
    return change_camera_settings(camera_hostname,'VIDEO','saturation', 4) 

def switch_to_default_sharpness(camera_hostname):
    return change_camera_settings(camera_hostname,'VIDEO','sharpness', 7) 

def switch_to_default_exposure(camera_hostname):
    return change_camera_settings(camera_hostname,'VIDEO','exposure', 4) 
    
def switch_to_default_contrast(camera_hostname):
    return change_camera_settings(camera_hostname,'VIDEO','contrast', 4) 


import getpass
import logging
import argparse

import os
import sys
import atexit
import time

import cv2
import numpy as np
from matplotlib import pyplot as plt

import gateway_util as gu
import camera_util as cu
import models

# Colors to draw detected boxes for LEDs
COLORS=[(255,0,0),(0,255,0),(0,0,255),(255,255,255),(128,128,128)]
CLASSES=['S','U', 'I', 'P', 'W']
#Functions to test
FUNCTIONS_TO_TEST = ['wifi_test','wps_test','broadband_test','status_test','internet_test','voice1_test']
# SIZE - have to be the size of CNN input
CNN_INPUT_W=640
CNN_INPUT_H=640

datetime='_'.join(str(t) for t in time.localtime()[:6])

#Logging setup
LOG_FILE = 'pure-ed500_led_test_'+datetime+'.log'
CONFIG_BEFORE_TEST = 'config.txt'
LOG_DIR='./pure-ed500_led_test_log_'+ datetime
os.mkdir(LOG_DIR)

"""Maps router LED name on the detected LED index
Args:
led_name: str 'status','uplink','internet','voice' or 'wireless' 
isOrderReversed: 1 or 0. Reversed order is 4,3,2,1,0 
    otherwise, order is not reversed.
Returns:
index of detected LED that corresponds to the led name (from 0 to 4)
"""
def map_to_visible_led (led_name,isOrderReversed):
    visible_led_idx = None
    if 'status' in led_name:
        visible_led_idx  = 0+4*isOrderReversed
    elif 'uplink' in led_name:
        visible_led_idx  = 1+2*isOrderReversed
    elif 'internet' in led_name:
        visible_led_idx  = 2
    elif 'voice' in led_name:
        visible_led_idx  = 3-2*isOrderReversed
    elif 'wireless' in led_name:
        visible_led_idx  = 4-4*isOrderReversed
    return visible_led_idx 

"""Counts eucledean distance between frame and off-frame
Args:
off_hsv: off-frame of size MxNx3 in HSV color space 
led_hsv: frame of same size as off_hsv in HSV color space
Returns:
eucledean distance (matrix of size MxNx1) in HSV space between frame and off-frame
"""
def hsv_distance_between_pxls(off_hsv, led_hsv):
    off_h, off_s, off_v =cv2.split(off_hsv)
    off_h=np.float32(off_h) /255.0  
    off_s=np.float32(off_s) /255.0  
    off_v=np.float32(off_v) /255.0
    
    led_h, led_s, led_v =cv2.split(led_hsv)
    led_h=np.float32(led_h) /255.0  
    led_s=np.float32(led_s) /255.0  
    led_v=np.float32(led_v) /255.0
    euc_dist=np.zeros_like(led_v)
    
    for i in range(off_h.shape[0]):
        for j in range(off_h.shape[1]):
            x=off_v[i,j]*off_s[i,j]*np.cos(2*np.pi*off_h[i,j])
            x_prim=led_v[i,j]*led_s[i,j]*np.cos(2*np.pi*led_h[i,j])
            y=off_v[i,j]*off_s[i,j]*np.sin(2*np.pi*off_h[i,j])
            y_prim=led_v[i,j]*led_s[i,j]*np.sin(2*np.pi*led_h[i,j])
            z=off_v[i,j]
            z_prim=led_v[i,j]
            euc_dist[i,j]=np.sqrt((x-x_prim)**2 + (y-y_prim)**2 + (z-z_prim)**2)
    return euc_dist        

"""Analazes frames and returns LED behavior and color
Args:
frames: the list of frames of size MxNx3 acquired during 5 seconds. 
    have to be over 160.
night: 1 or 0. Information about environment 
    (if lights in the lab are off, should be 1, otherwise 0).
off: a frame of size MxNx3 (same as size of each frame in frames argument)

Returns:
(color, behavior): color is the str 'green', 'orange', 'off' or 'red'
behavior: str 'CONSTANT', 'FLASH_FAST' or 'FLASH_SLOW'
"""
def whichBehavior(frames,night,off,LED):
    #THRESHOLDS
    #Saturation threshold to filter out too white areas in the dark conditions.
    SAT_THR=15    
    #HSV eucledean distance threshold to filter out pxls that changed color
    HSV_DIST_THR=0.2
    #Fraction of changed pxls in order 
    # to consider that the LED color is different from off state.
    CHANGED_COLOR_FRACTION_THR = 0.01
    #The difference between 'a' and 'b' channels in L*a*b* space 
    # is lower for orange and higher for red.  
    RED_ORANGE_a_b_diff_THR = 24 if night else 35

    color='off'
    behavior=''
    colors=[]  
    off_hsv=cv2.cvtColor(off,cv2.COLOR_BGR2HSV)
    off_Lab=cv2.cvtColor(off,cv2.COLOR_BGR2LAB)
    off_L,off_a,off_b=cv2.split(off_Lab)
    off_h,off_s,off_v=cv2.split(off_hsv)
    logging.debug('mean off L: ' + str(np.mean(off_L)))
    logging.debug('mean off a: ' + str(np.mean(off_a)))
    logging.debug('mean off b: ' + str(np.mean(off_b)))
    logging.debug('mean off h: ' + str(np.mean(off_h)))
    logging.debug('mean off s: ' + str(np.mean(off_s)))
    logging.debug('mean off v: ' + str(np.mean(off_v)))
    logging.debug('frames: ' + str(len(frames)))
    logging.debug('hsv dist thr: ' + str(HSV_DIST_THR))
    logging.debug('fraction thr: ' + str(CHANGED_COLOR_FRACTION_THR))
    
    #colored_fraction is for debugging
    colored_fractions =[] 
    #lists of means over 'a' channel, and means over 'b' channel
    a_means, b_means =[],[]   
    for i in range(len(frames)-1):
        led=frames[i].copy()              
        #hsv_dist:
        led_hsv=cv2.cvtColor(led,cv2.COLOR_BGR2HSV)
        hsv_dist=hsv_distance_between_pxls(off_hsv,led_hsv)
        #mask to filter pxls that changed color
        mask= (hsv_dist >= HSV_DIST_THR).astype(np.uint8)*255               
        #mask to filter out "too white" pxls
        if night:
            _,led_s,_ = cv2.split(led_hsv)
            mask_sat = (led_s > SAT_THR).astype(np.uint8)*255
            #combined mask
            mask=cv2.bitwise_and(mask,mask_sat)
            
        #Apply mask to filter color pxls    
        led_thr=cv2.bitwise_and(led,led, mask=mask)   

        #Reshape to list of pxls
        led_thr_reshaped=np.squeeze(led_thr.reshape(1,-1,3))
        
        #extract color pxls
        changed_pxls=np.delete(led_thr_reshaped, np.where(led_thr_reshaped==[0,0,0]),axis=0) 

        #count fraction of pxls that changed color 
        colored_fractions.append(changed_pxls.shape[0]/(led.shape[0]*led.shape[1]))
                
        #if less than certain fraction threshold - 
        # consider color didn't change, do not analyze it.
        if colored_fractions[-1] <= CHANGED_COLOR_FRACTION_THR:
            colors.append(0)
            continue  

        #analize the color if it was changed
        colors.append(1)

        #find 'a' channel mean and 'b' channel mean
        #Assumption: when LED responds to object state change, 
        #it doesn't change the base color (only one LED respond, and that LED has only one color)   
        changed_Lab=cv2.cvtColor(np.expand_dims(changed_pxls,axis=0),cv2.COLOR_BGR2Lab)
        changed_a=changed_Lab[:,:,1].flatten()
        changed_b=changed_Lab[:,:,2].flatten()

        changed_a_mean=np.mean(changed_a)
        changed_b_mean=np.mean(changed_b)

        a_means.append(changed_a_mean)
        b_means.append(changed_b_mean)

    logging.debug('max fraction: ' + str(np.max(colored_fractions)) + ' min fraction: ' + str(np.min(colored_fractions)))

    #number of frames that didn't change the color
    non_off_frames = np.count_nonzero(colors)
    logging.debug('color frames: ' + str(non_off_frames))
    #reduce the list from form 11110000111110000111 to form 10101. 
    colors=[value for idx, value in enumerate(colors) if idx==0 or value!=colors[idx-1]]
    #the number of times the color changed during the test time
    number_of_switches = len(colors)
        
    #find channel average over all ON frames
    if non_off_frames > 3:
        a_means_avg=np.mean(a_means)
        b_means_avg=np.mean(b_means)

        logging.debug('a_means avg: ' + str(a_means_avg)) 
        logging.debug('b_means avg: ' + str(b_means_avg)) 

        #green is usually closer to green on the scale green-red,
        #since the middle is 128, if the 'a' channel is lower than 128,
        # the LED is green 
        if a_means_avg < 128:
            color='green'    
        #The red and orange are too close to each other, 
        # but orange has less difference between 'a' and 'b' channel:    
        elif abs(b_means_avg - a_means_avg) < RED_ORANGE_a_b_diff_THR:
            color='orange'
        elif abs(b_means_avg - a_means_avg) >= RED_ORANGE_a_b_diff_THR:
            color='red'
       
    #constant behavior is either on or off
    if number_of_switches < 4 or color == 'off':
        behavior='CONSTANT'

    #during 5 seconds with 30 fps we get approx 150 frames (in reality 166-168)
    #When FLASH_SLOW there are approx 6 - 7 changes, 
    #when FLASH_FAST - around 22 - 23 changes.  
    elif number_of_switches < 13:
        behavior='FLASH_SLOW'
    else:
        behavior='FLASH_FAST'
           
    logging.debug('switches under 5s: ' + str(number_of_switches))
  
    return(color,behavior)

'''Test the LEDs on the Pure ed500 RGW'''
def pure_ed500_led_test(rgw_hostname, rgw_port, rgw_username, rgw_pass,camera_hostname):
    test_failed=False
    #connect to the rgw
    logging.debug('Connecting to RGW...')    
    try: ssh=gu.get_ssh(rgw_hostname, rgw_port, rgw_username, rgw_pass)
    except Exception: sys.exit('Failed to connect to the RGW')

    #connect to IP camera
    logging.debug('Connecting to IP camera...')
    if not cu.isConnected(camera_hostname): sys.exit('Failed to connect to IP camera')

    #load model 
    logging.debug('Loading model...')
    try: model=models.LedsSchemeModel()
    except Exception: sys.exit('Failed to load model')

    #switch camera to defaults
    logging.debug('Switching camera to defaults...')
    r_sat=cu.switch_to_default_saturation(camera_hostname) 
    r_sha=cu.switch_to_default_sharpness(camera_hostname)
    r_exp=cu.switch_to_default_exposure(camera_hostname)
    r_con=cu.switch_to_default_contrast(camera_hostname)
    r_auto=cu.switch_to_auto_mode(camera_hostname)
    if r_sat and r_sha and r_exp and r_con and r_auto: time.sleep(3)
    else: sys.exit('Failed to switch to defaults')

    night=0
    #Take a picture and detect leds, twice if needed
    for i in range(0,2):
        logging.debug('Shooting...')
        img=cu.shoot(camera_hostname,CNN_INPUT_W,CNN_INPUT_H)
        if img is not None: cv2.imwrite(os.path.join(LOG_DIR,'original.jpg'), img)
        else: sys.exit('Failed to acquire an image')
        
        #Detect leds
        logging.debug('Detecting leds...')
        leds=model.detect(img)
        logging.debug('Postprocessing detection...')
        order=[led['class'] for led in leds]
        isOrderReversed=(order==[4,3,2,1,0])
        isOrderCorrect = (order== [0,1,2,3,4] or isOrderReversed)
        if isOrderCorrect: break
        elif i : sys.exit('Failed to correctly detect leds')

    #Saving an image with detected leds
    logging.debug('Saving detected.jpg...')
    for led in leds:
        y_UL=int(led['box'][0])
        x_UL=int(led['box'][1])
        y_BR=int(led['box'][2])
        x_BR=int(led['box'][3])
        img=cv2.rectangle(img, (x_UL,y_UL),(x_BR,y_BR),COLORS[led['class']],1)
        img=cv2.putText(img,str(CLASSES[led['class']]), (x_UL,y_UL-4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLORS[led['class']])
    cv2.imwrite(os.path.join(LOG_DIR,'detected.jpg'), img)

    #Get the infrared filter state
    logging.debug('Getting IR filter state...')
    resp, night = cu.isInfraredOn(camera_hostname)
    if not resp: sys.exit('Failed to get IR filter info')
    else: logging.debug('filter: ' + str(night))

    #Switch camera to daylight mode
    logging.debug('Switching camera to daylight mode...')
    resp=cu.switch_to_day_mode(camera_hostname)
    if resp: time.sleep(3)
    else: sys.exit('Failed to switch to daylight mode')

    #Read and copy the config   
    logging.debug('Getting gateway configs...') 
    try: config = gu.read_and_copy_config(ssh, os.path.join(LOG_DIR,CONFIG_BEFORE_TEST))
    except Exception: sys.exit('Failed to read and copy config file')

    #Get mapping, command to change config, and command to change config back
    (mapping, uci_c)=gu.get_mapping_and_uci_command_to_change_config(config)

    #Change config
    logging.debug('Changing gateway configs...') 
    if not gu.run_uci_command(ssh,uci_c) and not (gu.revert(ssh)):
        sys.exit('Failed to execute uci command and revert staged. See original config in log folder')

    #If something goes wrong, change config back.
    def exit_handler():
        logging.error(' ! Something went terribly wrong !\n Trying to change the config back...')
        gu.reset_to_default(ssh)
    atexit.register(exit_handler)

    #Get command - behavior dictionary
    command_behavior_dict = gu.get_command_and_expected_behavior_dict(mapping,FUNCTIONS_TO_TEST)
    
    #If not dark, set high saturation
    logging.debug('Switching to high saturation...')
    if not night:
        r_sat = cu.switch_to_high_saturation(camera_hostname)
        if r_sat: time.sleep(3)  
        else: sys.exit('Failed to switch to high saturation')
        
    #Take an image where all LEDs are off
    logging.debug('Take all OFF image...')
    img_day_mode=cu.shoot(camera_hostname,CNN_INPUT_W,CNN_INPUT_H)
    if img_day_mode is None: sys.exit('Failed to acquire an image')

    #Vars to keep which led is being tested to switch off after the test
    current_led_to_check_idx = None
    command_to_switch_off_current_led = '' 
    
    #Test the led   
    for command, (LED, LED_color, LED_behavior) in command_behavior_dict.items():         
                
        #find led box
        led_to_check_idx = map_to_visible_led(LED, isOrderReversed)
        
        y_UL=int(leds[led_to_check_idx]['box'][0])
        x_UL=int(leds[led_to_check_idx]['box'][1])
        y_BR=int(leds[led_to_check_idx]['box'][2])
        x_BR=int(leds[led_to_check_idx]['box'][3])        
        w, h = x_BR - x_UL, y_BR - y_UL
        logging.info('command: {0}'.format(command))
        logging.info('led: {0}'.format(LED))
        
        #if next LED is tested, switch off the current one so that the light from it 
        #doens't 'leak' to neighboring LEDs 
        if current_led_to_check_idx is not None and current_led_to_check_idx != led_to_check_idx:
            logging.debug('Switching off current ')
            _, _,stderr = ssh.exec_command(command_to_switch_off_current_led)
            err=stderr.readlines()
            if err !=[]: sys.exit('Could not execute command ' + command_to_switch_off_current_led)  
        
        current_led_to_check_idx = led_to_check_idx

        #memorize command to switch off the led
        if LED_behavior == 'OFF' or (LED_color == 'off' and LED_behavior == 'ON'):
            command_to_switch_off_current_led = command

        _, _, stderr = ssh.exec_command(command)
        err=stderr.readlines()
        if err !=[]: sys.exit('Could not execute command ' + command)
        
        time.sleep(0.3)            
        #enlarge detected box
        frames_y_UL = max(0,y_UL-h)
        frames_x_UL = max(0,x_UL-w)
        frames_y_BR = min(CNN_INPUT_H,y_BR+h)
        frames_x_BR = min(CNN_INPUT_W,x_BR+w)
        #cut the corresponding area from off image
        off = img_day_mode[frames_y_UL:frames_y_BR,frames_x_UL:frames_x_BR]
        #get frames 
        frames = cu.video(camera_hostname,CNN_INPUT_W,CNN_INPUT_H,frames_y_UL,frames_x_UL,frames_y_BR,frames_x_BR,5)    
        if frames is None: sys.exit('Failed to acquire frames')    
        logging.debug('Detecting behavior...')
        (detected_color, detected_behavior) = whichBehavior(frames,night,off,LED)
        
        logging.info('expected color: {0} behavior: {1}'.format(LED_color, LED_behavior))    
        logging.info('detected color: {0} behavior: {1}'.format(detected_color, detected_behavior))

        if (LED_color=='off' or LED_behavior=='OFF') and detected_color == 'off' and detected_behavior == 'CONSTANT':
            logging.info('CORRECT')
        elif LED_color==detected_color and \
            (LED_behavior == detected_behavior or (LED_behavior=='ON' and detected_behavior=='CONSTANT')):
            logging.info('CORRECT')
        else:
            test_failed=True
            #save the frames:
            for i in range(0, len(frames)):
                file_name=LED + '_' + LED_color + '_' + LED_behavior + '_f_' + str(i) + '.jpg'
                cv2.imwrite(os.path.join(LOG_DIR, file_name), frames[i])
            logging.error('WRONG') 

    atexit.unregister(exit_handler)
    cu.reset_to_default(camera_hostname)
    gu.reset_to_default(ssh)
    return test_failed

def main(argv):
    arg_parser=argparse.ArgumentParser(description='test LEDs. Run defaultreset before')
    arg_parser.add_argument('-v', '--verbose', action='store_true', help='verbose output')
    arg_parser.add_argument('gateway_ip', help='gateway IP address')
    arg_parser.add_argument('-p', '--port', type=int, default=22, help= 'gateway ssh port (default 22)')
    arg_parser.add_argument('gateway_user', help='gateway user')
    arg_parser.add_argument('camera_ip', help='camera IP address')

    args=arg_parser.parse_args()
    gateway_pwd = getpass.getpass(prompt='Enter password for {0} {1}: '.format(args.gateway_ip,args.gateway_user))
    
    #logging configuration
    
    logging_level=logging.DEBUG if args.verbose else logging.INFO
    logging.getLogger("tensorflow").setLevel(logging.ERROR)
    logging.getLogger("paramiko").setLevel(logging.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.ERROR)
    logging.basicConfig(level=logging_level)
    logFormatter = logging.Formatter("%(asctime)s [%(levelname)-5.5s]  %(message)s", "%Y-%m-%d %H:%M:%S")
    rootLogger = logging.getLogger()

    fileHandler = logging.FileHandler(os.path.join(LOG_DIR , LOG_FILE))
    fileHandler.setFormatter(logFormatter)
    rootLogger.addHandler(fileHandler)

    failed = pure_ed500_led_test(args.gateway_ip, args.port, args.gateway_user,gateway_pwd, args.camera_ip)
    if not failed: logging.info('all LEDs work as expected')
    else: logging.info('Some LEDs do not work as expected, see the log file: ' + LOG_FILE)

if __name__ == "__main__":
    main(sys.argv)
    

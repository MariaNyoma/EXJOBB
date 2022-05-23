from json.encoder import INFINITY
import tensorflow as tf
import paths
import numpy as np
import cv2
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

def get_detections(img,detection_fn):
    image_np = np.array(img)
    input_tensor=tf.convert_to_tensor (np.expand_dims(image_np,0),  dtype=tf.uint8)
    detections = detection_fn(input_tensor)
    num_detections = int(detections.pop('num_detections'))
    detections = {key: value[0, : num_detections].numpy()
                for key, value in detections.items()}
    detections['num_detections'] = num_detections
    detections['detection_classes'] = detections['detection_classes'].astype(np.int64) -1   
    return detections

def sort_leds(leds_detections):
    #find leds with highest scores and different classes
    leds=[]
    min_y=INFINITY
    min_x=INFINITY
    max_y=-INFINITY
    max_x=-INFINITY
    for idx in range(5):
        led={}
        led['class']=leds_detections['detection_classes'][idx]
        led['box']=leds_detections['detection_boxes'][idx]
        led['score']=leds_detections['detection_scores'][idx]
        leds.append(led)
        min_y=min(min_y,leds_detections['detection_boxes'][idx][0])
        min_x=min(min_x,leds_detections['detection_boxes'][idx][1])
        max_y=max(max_y,leds_detections['detection_boxes'][idx][2])
        max_x=max(max_x,leds_detections['detection_boxes'][idx][3])
        
    #define display orientation and sort the list of leds by box position
    vertical=max_y-min_y>max_x-min_x
    if vertical:            
        leds.sort(key= lambda x: x['box'][0])                                
    else:            
        leds.sort(key= lambda x: x['box'][1])
    return leds
               
class LedsSchemeModel:
    def __init__(self):
            self.detect_fn=tf.saved_model.load(globals.LEDS_SCHEME_MODEL_PATH)
    def detect(self, img):
        detections=get_detections(img, self.detect_fn)
        leds = sort_leds(detections)
        #bring box coordinates to absolute values:
        for led in leds:
            led['box'][0]=round(led['box'][0]*img.shape[0])
            led['box'][1]=round(led['box'][1]*img.shape[1])
            led['box'][2]=round(led['box'][2]*img.shape[0])
            led['box'][3]=round(led['box'][3]*img.shape[1])
        return leds

class DisplayLedsSchemeModel:
    def __init__(self):
        self.detect_display_fn=tf.saved_model.load(globals.DISPLAY_MODEL_PATH)
        self.detect_led_fn=tf.saved_model.load(globals.LEDS_MODEL_PATH)

    def detect(self, img):
        display_detections=get_detections(img, self.detect_display_fn)
    
        y_UL=round(display_detections['detection_boxes'][0][0]*img.shape[0])
        x_UL=round(display_detections['detection_boxes'][0][1]*img.shape[1])
        y_BR=round(display_detections['detection_boxes'][0][2]*img.shape[0])
        x_BR=round(display_detections['detection_boxes'][0][3]*img.shape[1])
        
        #cut display from image
        display = img[y_UL:y_BR, x_UL:x_BR]
        leds_detections = get_detections(display, self.detect_led_fn)
        leds = sort_leds(leds_detections)
        #bring box coordinates to absolute values:
        for led in leds:
            led['box'][0]=round(led['box'][0]*display.shape[0])+y_UL
            led['box'][1]=round(led['box'][1]*display.shape[1])+x_UL
            led['box'][2]=round(led['box'][2]*display.shape[0])+y_UL
            led['box'][3]=round(led['box'][3]*display.shape[1])+x_UL    
        return leds
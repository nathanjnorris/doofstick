import board
import neopixel
import analogio
import pwmio
import simpleio
import time
import array
import math
import random
import adafruit_lis3dh
from digitalio import DigitalInOut, Direction, Pull
from adafruit_debouncer import Button
from adafruit_simplemath import map_range, constrain
from rainbowio import colorwheel

# Constants
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
OFF = (0, 0, 0)

# NeoPixel setup
external_power = DigitalInOut(board.EXTERNAL_POWER)
external_power.direction = Direction.OUTPUT
external_power.value = False
led_pin = board.EXTERNAL_NEOPIXELS
n_pixels = 129
pixel = neopixel.NeoPixel(led_pin, n_pixels, auto_write=False, brightness=0.5)

# Potentiometer setup
pot_twist = analogio.AnalogIn(board.A1)
pot_slide = analogio.AnalogIn(board.A0)

# Global brightness variables
global_brightness = 0.5  # Start at 50% brightness
brightness_smooth = 0.5  # For smooth transitions

# Button setup
button_pin = DigitalInOut(board.EXTERNAL_BUTTON)
button_pin.direction = Direction.INPUT
button_pin.pull = Pull.UP
switch = Button(button_pin, long_duration_ms=500)

# RGB LED setup
red_led = pwmio.PWMOut(board.D12)
green_led = pwmio.PWMOut(board.D10)
blue_led = pwmio.PWMOut(board.D11)

# Microphone setup
mic = analogio.AnalogIn(board.A2)

# Accelerometer setup
i2c = board.I2C()
int1 = DigitalInOut(board.ACCELEROMETER_INTERRUPT)
lis3dh = adafruit_lis3dh.LIS3DH_I2C(i2c, int1=int1)
lis3dh.range = adafruit_lis3dh.RANGE_2_G

# Auto mode switcher variables
auto_time = 600  # 10 minutes in seconds
last_interaction_time = time.monotonic()

# Update brightness variables
MIN_BRIGHTNESS = 0.05  # 5% minimum brightness
MAX_BRIGHTNESS = 1.0   # 100% maximum brightness

# Sound reactive constants and variables
dc_offset = 0
noise = 100
samples = 60
top = n_pixels // 2
peak = 0
vol_count = 0
lvl = 10
min_level_avg = 0
max_level_avg = 512
vol = array.array('H', [0] * samples)
spin_position = 0.0

# Variables for color wheel mode
wave_position = n_pixels // 2  # Start at the top of the circle
WAVE_WIDTH = 20  # Minimum width of the wave effect
current_hue = 0  # Start with red (0 on the color wheel)
next_hue = 0  # Initialize next_hue
MIN_WAVE_SPEED = 1 # Minimum speed (adjust as needed)
MAX_WAVE_SPEED = 5  # Maximum speed (adjust as needed)
DEFAULT_BRIGHTNESS = 0.5  # 75% default brightness
WAVE_DIP = 0.1  # Minimum brightness at wave center (0.2 means 80% dimmer than default)
MIN_COLOR_STEP = 10  # Minimum color wheel step
MAX_COLOR_STEP = 30  # Maximum color wheel step (adjust as needed)
COS_TABLE = array.array('f', [math.cos(math.pi * i / 128) for i in range(129)]) # Pre-calculate cosine values

# Blinking LED variables
last_blink_time = 0
blink_interval = 0.5
led_state = False

# Wine glass mode variables
last_brightness = 0.1
target_brightness = 0.1

# Rain variables
rain_drops = []
MAX_DROPS = 50
MIN_RAIN = 10  # Minimum number of raindrops
RAIN_COLOR = (0, 20, 100)  # Blue color for rain
MIN_CLOUD_SIZE = 15
MAX_CLOUD_SIZE = 40

def should_change_mode():
    global last_interaction_time
    current_time = time.monotonic()
    if current_time - last_interaction_time >= auto_time:
        last_interaction_time = current_time
        return True
    return False

def reset_interaction_timer():
    global last_interaction_time
    last_interaction_time = time.monotonic()

def set_rgb_led(color):
    red_led.duty_cycle = int(simpleio.map_range(color[0], 0, 255, 65535, 0))
    green_led.duty_cycle = int(simpleio.map_range(color[1], 0, 255, 65535, 0))
    blue_led.duty_cycle = int(simpleio.map_range(color[2], 0, 255, 65535, 0))

def update_blinking_led(color):
    global last_blink_time, led_state
    current_time = time.monotonic()
    if current_time - last_blink_time >= blink_interval:
        last_blink_time = current_time
        led_state = not led_state
        set_rgb_led(color if led_state else OFF)

def update_global_brightness(sound_level):
    global global_brightness, brightness_smooth
    target_brightness = map_range(sound_level, 0, top, 0.1, 1.0)
    target_brightness = constrain(target_brightness, 0.1, 1.0)
    brightness_smooth = brightness_smooth * 0.9 + target_brightness * 0.1
    global_brightness = brightness_smooth

def update_brightness():
    flipped_value = 65535 - pot_twist.value
    brightness = MIN_BRIGHTNESS + (flipped_value * (MAX_BRIGHTNESS - MIN_BRIGHTNESS) / 65535)
    pixel.brightness = max(MIN_BRIGHTNESS, min(MAX_BRIGHTNESS, brightness))

def color_wheel_mode():
    global wave_position, current_hue, next_hue
    
    inverted_slide = 65535 - pot_slide.value
    wave_speed = MIN_WAVE_SPEED + ((inverted_slide * (MAX_WAVE_SPEED - MIN_WAVE_SPEED)) // 65535)
    
    inverted_twist = 65535 - pot_twist.value
    color_step = MIN_COLOR_STEP + ((inverted_twist * (MAX_COLOR_STEP - MIN_COLOR_STEP)) // 65535)
    
    # Move the wave downwards
    old_wave_position = wave_position
    wave_position = (wave_position - wave_speed) % (n_pixels // 2)
    
    # Update next_hue continuously
    next_hue = (current_hue + color_step) % 256
    
    # Only update current_hue when the wave passes the bottom
    if wave_position > old_wave_position:
        current_hue = next_hue
    
    current_color = colorwheel(int(current_hue))
    next_color = colorwheel(int(next_hue))
    
    brightness_range = DEFAULT_BRIGHTNESS - WAVE_DIP
    half_wave_width = WAVE_WIDTH // 2
    
    for i in range(n_pixels):
        if i < n_pixels // 2:
            distance = abs(i - wave_position)
            is_after_wave = i >= wave_position
        else:
            distance = abs((n_pixels - 1 - i) - wave_position)
            is_after_wave = (n_pixels - 1 - i) >= wave_position
        
        if distance < half_wave_width:
            cos_index = int(distance * 128 / half_wave_width)
            wave_brightness = WAVE_DIP + brightness_range * (1 - COS_TABLE[cos_index]) / 2
        else:
            wave_brightness = DEFAULT_BRIGHTNESS
        
        if is_after_wave:
            color = next_color
        else:
            color = current_color
        
        r = int(((color >> 16) & 255) * wave_brightness)
        g = int(((color >> 8) & 255) * wave_brightness)
        b = int((color & 255) * wave_brightness)
        
        pixel[i] = (r, g, b)
    
    pixel.brightness = DEFAULT_BRIGHTNESS
    pixel.show()
    
def update_pixel_color_all():
    out_colour = colorwheel(int(pot_slide.value / 256))
    pixel.fill(out_colour)
    pixel.show()

def sound_reactive_equalizer():
    global peak, vol_count, lvl, min_level_avg, max_level_avg

    n = int((mic.value / 65536) * 1000)
    n = abs(n - 512 - dc_offset)
    if n >= noise:
        n = n - noise

    lvl = int(((lvl * 7) + n) / 8)

    height = top * (lvl - min_level_avg) / (max_level_avg - min_level_avg)
    height = max(0, min(int(height), top))

    if height > peak:
        peak = height

    pixel.fill((0, 0, 0))

    base_hue = int(map_range(height, 0, top, 0, 255))

    # Determine which mode to use based on slide pot
    pot_value = pot_slide.value
    lower_threshold = 5000  
    upper_threshold = 60000

    def apply_brightness(color, brightness):
        r = (color >> 16) & 255
        g = (color >> 8) & 255
        b = color & 255
        return (int(r * brightness), int(g * brightness), int(b * brightness))

    if pot_value < lower_threshold:
        # Original mode
        for i in range(height):
            hue = (base_hue + int(map_range(i, 0, height, 0, 60))) % 256
            color = colorwheel(hue)
            pixel[i] = color
            pixel[n_pixels - 1 - i] = color

        if 0 < peak <= top:
            pixel[peak - 1] = (255, 255, 255)
            pixel[n_pixels - peak] = (255, 255, 255)

    elif pot_value > upper_threshold:
        # New center-out mode
        center = n_pixels // 2
        for i in range(height):
            hue = (base_hue + int(map_range(i, 0, height, 0, 60))) % 256
            color = colorwheel(hue)
            pixel[center + i] = color
            pixel[center - i - 1] = color

        if 0 < peak <= top:
            pixel[center + peak - 1] = (255, 255, 255)
            pixel[center - peak] = (255, 255, 255)

    else:
        # Transition zone: blend both modes
        blend_factor = (pot_value - lower_threshold) / (upper_threshold - lower_threshold)
        center = n_pixels // 2
        for i in range(height):
            hue = (base_hue + int(map_range(i, 0, height, 0, 60))) % 256
            color = colorwheel(hue)
            
            # Original mode (fading out)
            pixel[i] = apply_brightness(color, 1 - blend_factor)
            pixel[n_pixels - 1 - i] = apply_brightness(color, 1 - blend_factor)
            
            # New mode (fading in)
            pixel[center + i] = apply_brightness(color, blend_factor)
            pixel[center - i - 1] = apply_brightness(color, blend_factor)

        if 0 < peak <= top:
            peak_color_orig = apply_brightness(0xFFFFFF, 1 - blend_factor)
            pixel[peak - 1] = peak_color_orig
            pixel[n_pixels - peak] = peak_color_orig
            
            peak_color_new = apply_brightness(0xFFFFFF, blend_factor)
            pixel[center + peak - 1] = peak_color_new
            pixel[center - peak] = peak_color_new

    pixel.show()

    vol[vol_count] = n
    vol_count = (vol_count + 1) % samples

    min_level = max_level = vol[0]
    for i in range(1, len(vol)):
        if vol[i] < min_level:
            min_level = vol[i]
        elif vol[i] > max_level:
            max_level = vol[i]

    if (max_level - min_level) < top:
        max_level = min_level + top
    min_level_avg = (min_level_avg * 63 + min_level) >> 6
    max_level_avg = (max_level_avg * 63 + max_level) >> 6

def wine_glass_mode():
    global last_brightness, target_brightness

    x, y, z = lis3dh.acceleration
    acceleration_magnitude = math.sqrt(x*x + y*y + z*z)

    # Calculate target brightness based on acceleration
    new_target = map_range(acceleration_magnitude, 9.8, 20, 0.1, 1.0)
    new_target = constrain(new_target, 0.1, 1.0)
    
    # Update target brightness if new target is higher
    if new_target > target_brightness:
        target_brightness = new_target
    
    # Gradually move current brightness towards target
    brightness_diff = target_brightness - last_brightness
    last_brightness += brightness_diff * 0.1

    # Ensure minimum brightness of 15%
    last_brightness = max(0.15, last_brightness)
    
    # Decay target brightness (75% slower than original)
    target_brightness = max(0.1, target_brightness * 0.9875)

    shift = int(map_range(-x, -10, 10, -n_pixels//8, n_pixels//8))
    shift = max(-n_pixels//8, min(n_pixels//8, shift))
    
    min_fill = int(n_pixels * 0.25)
    max_fill = int(n_pixels * 0.75)
    fill_range = max_fill - min_fill
    
    fill_level = int(map_range(pot_slide.value, 0, 65535, 0, fill_range))
    fill_level += min_fill

    wine_color = colorwheel(int(pot_twist.value / 256))
    
    # Extract RGB values from the integer color
    r = (wine_color >> 16) & 255
    g = (wine_color >> 8) & 255
    b = wine_color & 255
    
    # Apply brightness to color
    r = int(r * last_brightness)
    g = int(g * last_brightness)
    b = int(b * last_brightness)
    bright_wine_color = (r, g, b)

    pixel.fill((0, 0, 0))
    
    for i in range(fill_level // 2):
        left_index = (i + shift) % n_pixels
        right_index = (n_pixels - 1 - i + shift) % n_pixels
        pixel[left_index] = pixel[right_index] = bright_wine_color

    pixel.show()

def sound_reactive_spinner():
    global vol_count, lvl, min_level_avg, max_level_avg, spin_position

    n = int((mic.value / 65536) * 1000)
    n = abs(n - 512 - dc_offset)
    if n >= noise:
        n = n - noise

    lvl = int(((lvl * 7) + n) / 8)

    # Calculate brightness based on sound level
    height = max(0, min(top, int((lvl - min_level_avg) * top / (max_level_avg - min_level_avg))))
    brightness = map_range(height, 0, top, 0.25, 1.0)
    brightness = constrain(brightness, 0.25, 1.0)

    # Get base color from pot_slide
    base_color = colorwheel(int(pot_slide.value / 256))

    # Apply brightness to color
    r = int(((base_color >> 16) & 255) * brightness)
    g = int(((base_color >> 8) & 255) * brightness)
    b = int((base_color & 255) * brightness)
    color = (r, g, b)

    # Calculate spin speed and direction based on pot_twist
    twist_value = pot_twist.value
    if twist_value < 32768:
        spin_speed = map_range(twist_value, 0, 32768, 0.007, 0)
    else:
        spin_speed = map_range(twist_value, 32768, 65535, 0, -0.007)
    
    spin_position += spin_speed
    spin_position = spin_position % 1.0  # Keep spin_position between 0 and 1

    # ... (rest of the function remains the same)
    # Determine LED pattern based on sound level
    if height < top // 4:
        gap = 8
    elif height < top // 2:
        gap = 4
    elif height < 3 * top // 4:
        gap = 2
    else:
        gap = 1

    # Check if sound level is high enough for strobing
    if gap == 1:
        # Strobe effect aligned with 140 BPM
        bpm = 140
        beat_duration = 60 / bpm  # Duration of one beat in seconds
        current_time = time.monotonic()
        if (current_time % beat_duration) < (beat_duration / 2):
            pixel.fill((int(255 * global_brightness),) * 3)  # White color for strobe
        else:
            pixel.fill(color)  # Base color between strobes
    else:
        # Normal spinning effect
        pixel.fill((0, 0, 0))
        for i in range(n_pixels):
            if i % gap == 0:
                pixel_index = int((i + spin_position * n_pixels) % n_pixels)
                pixel[pixel_index] = color

    pixel.show()

    # Update volume levels
    vol[vol_count] = n
    vol_count = (vol_count + 1) % samples

    min_level = max_level = vol[0]
    for i in range(1, len(vol)):
        if vol[i] < min_level:
            min_level = vol[i]
        elif vol[i] > max_level:
            max_level = vol[i]

    # Adjust min and max levels more dynamically
    if min_level < min_level_avg:
        min_level_avg = min_level
    else:
        min_level_avg = (min_level_avg * 63 + min_level) >> 6

    if max_level > max_level_avg:
        max_level_avg = max_level
    else:
        max_level_avg = (max_level_avg * 63 + max_level) >> 6

    # Ensure there's always a minimum range between min and max levels
    if (max_level_avg - min_level_avg) < 100:
        max_level_avg = min_level_avg + 100

    # Update volume levels
    vol[vol_count] = n
    vol_count = (vol_count + 1) % samples

    min_level = max_level = vol[0]
    for i in range(1, len(vol)):
        if vol[i] < min_level:
            min_level = vol[i]
        elif vol[i] > max_level:
            max_level = vol[i]

    # Adjust min and max levels more dynamically
    if min_level < min_level_avg:
        min_level_avg = min_level
    else:
        min_level_avg = (min_level_avg * 63 + min_level) >> 6

    if max_level > max_level_avg:
        max_level_avg = max_level
    else:
        max_level_avg = (max_level_avg * 63 + max_level) >> 6

    # Ensure there's always a minimum range between min and max levels
    if (max_level_avg - min_level_avg) < 100:
        max_level_avg = min_level_avg + 100

def rain_mode():
    global rain_drops
    
    # Get tilt from accelerometer
    x, _, _ = lis3dh.acceleration
    
    # Map tilt to shift value (inverted)
    shift = int(map_range(x, -10, 10, n_pixels//4, -n_pixels//4))
    shift = max(-n_pixels//4, min(n_pixels//4, shift))
    
    # Invert the slide pot value
    inverted_slide = 65535 - pot_slide.value
    
    # Control rain intensity and cloud darkness with inverted slide potentiometer
    rain_intensity = int(map_range(inverted_slide, 0, 65535, MIN_RAIN, MAX_DROPS))
    cloud_darkness = int(map_range(inverted_slide, 0, 65535, 100, 5))  # 200 (light) to 50 (dark)
    
    # Control cloud size with twist potentiometer
    CLOUD_SIZE = int(map_range(65535 - pot_twist.value, 0, 65535, MIN_CLOUD_SIZE, MAX_CLOUD_SIZE))
    
    # Calculate cloud position
    cloud_center = (n_pixels // 2 + shift) % n_pixels
    cloud_start = (cloud_center - CLOUD_SIZE // 2) % n_pixels
    cloud_end = (cloud_center + CLOUD_SIZE // 2) % n_pixels
    
    # Calculate maximum travel distance for raindrops
    max_travel = n_pixels // 2 - CLOUD_SIZE // 2
    
    # Create new raindrops
    while len(rain_drops) < rain_intensity:
        # Randomly choose left or right side of the cloud
        side = random.choice([-1, 1])
        start_pos = cloud_start if side == -1 else cloud_end
        new_drop = {
            "position": start_pos,
            "side": side,
            "brightness": 1.0,
            "speed": random.uniform(0.5, 2.0),  # Variable speed for each drop
            "distance": 0  # Track distance traveled
        }
        rain_drops.append(new_drop)
    
    # Clear all pixels
    pixel.fill((0, 0, 0))
    
    # Draw cloud
    for i in range(CLOUD_SIZE):
        cloud_pixel = (cloud_start + i) % n_pixels
        pixel[cloud_pixel] = (cloud_darkness, cloud_darkness, cloud_darkness)  # Gray color for the cloud
    
    # Update and draw raindrops
    for drop in rain_drops:
        # Move raindrop down
        if drop["side"] == -1:
            drop["position"] = (drop["position"] - drop["speed"]) % n_pixels
        else:
            drop["position"] = (drop["position"] + drop["speed"]) % n_pixels
        
        drop["distance"] += drop["speed"]
        
        # Apply brightness to color
        r = int(RAIN_COLOR[0] * drop["brightness"])
        g = int(RAIN_COLOR[1] * drop["brightness"])
        b = int(RAIN_COLOR[2] * drop["brightness"])
        
        pixel[int(drop["position"])] = (r, g, b)
        
        # Fade out raindrop
        drop["brightness"] *= 0.98
    
    # Remove raindrops that have reached the bottom or faded out
    rain_drops = [drop for drop in rain_drops if 
                  drop["distance"] < max_travel and
                  drop["brightness"] > 0.05]
    
    pixel.brightness = 0.5
    pixel.show()

mode = 0
while True:
    switch.update()
    
    # Check for mode change due to inactivity
    if mode != 0 and should_change_mode():
        mode = (mode % 4) + 1  # Change to next mode, looping back to 1 after 4
        set_rgb_led(OFF)
        time.sleep(0.5)
        set_rgb_led(GREEN)
    
    if switch.short_count == 1 or switch.long_press:
        reset_interaction_timer()
    
    if mode == 0:  # Wait for startup
        update_blinking_led(GREEN)
        if switch.short_count == 1:
            mode = 1
            external_power.value = True
            set_rgb_led(GREEN)
            reset_interaction_timer()
    elif mode == 1:  # Solid colour mode
        update_brightness()
        update_pixel_color_all()
        if switch.short_count == 1:
            pixel.fill((0, 0, 0))
            pixel.show()
            external_power.value = False
            mode = 0
        if switch.long_press:
            set_rgb_led(OFF)
            time.sleep(0.5)
            set_rgb_led(GREEN)
            mode = 2
    elif mode == 2:  # Color wheel mode
        update_brightness()  # Use the twist pot for brightness in this mode
        color_wheel_mode()
        if switch.short_count == 1:
            pixel.fill((0, 0, 0))
            pixel.show()
            external_power.value = False
            mode = 0
        if switch.long_press:
            set_rgb_led(OFF)
            time.sleep(0.5)
            set_rgb_led(GREEN)
            mode = 3
    elif mode == 3:  # Sound reactive eqaulizer mode
        pixel.brightness = 1.0  # Set full brightness, will be modulated by sound
        sound_reactive_equalizer()
        if switch.short_count == 1:
            pixel.fill((0, 0, 0))
            pixel.show()
            external_power.value = False
            mode = 0
        if switch.long_press:
            set_rgb_led(OFF)
            time.sleep(0.5)
            set_rgb_led(GREEN)
            mode = 4
    elif mode == 4:  # Sound reactive spinner mode
        pixel.brightness = 1.0  # Set full brightness, will be modulated by sound
        sound_reactive_spinner()
        if switch.short_count == 1:
            pixel.fill((0, 0, 0))
            pixel.show()
            external_power.value = False
            mode = 0
        if switch.long_press:
            set_rgb_led(OFF)
            time.sleep(0.5)
            set_rgb_led(GREEN)
            mode = 5
    elif mode == 5:  # Wine glass mode
        wine_glass_mode()
        if switch.short_count == 1:
            pixel.fill((0, 0, 0))
            pixel.show()
            external_power.value = False    
            mode = 0
        if switch.long_press:
            set_rgb_led(OFF)
            time.sleep(0.5)
            set_rgb_led(GREEN)
            mode = 6
    elif mode == 6:  # Rain mode
        rain_mode()
        if switch.short_count == 1:
            pixel.fill((0, 0, 0))
            pixel.show()
            external_power.value = False    
            mode = 0
        if switch.long_press:
            set_rgb_led(OFF)
            time.sleep(0.5)
            set_rgb_led(GREEN)
            mode = 7  # Switch to new snake mode
    
    # Gradually lower the peak in sound reactive equalizer mode
    if mode == 3 and peak > 0:
        peak = peak - 1

    time.sleep(0.01)  # Smaller delay for more responsive button checks
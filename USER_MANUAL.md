# Handtracking Theremin User Manual

[日本語](USER_MANUAL_ja.md) · [README](README.md)

Play this instrument by moving your hands in front of a webcam to change pitch, volume, and tone. This manual covers the main interface opened with the Launch file. You do not need to edit any code.

**For your first session, follow sections 1–3 to start playing.** If setup is already complete, open the Launch file and press **Start**. To silence the sound immediately, press **PANIC / F12**.

Button and setting names appear in **bold** as they do on screen. This manual describes the implementation as of October 30, 2026.

## Contents

- [1. Get ready](#prepare)
- [2. Launch and choose your audio output](#launch)
- [3. Play with your hands](#play)
- [4. Find and arrange the panels](#panels)
- [5. Set the pitch range and scale](#pitch)
- [6. Shape your sound](#tone)
- [7. Use effects](#effects)
- [8. Control effects with gestures or keys](#gestures)
- [9. Play external audio alongside the instrument](#thru)
- [10. Save and recall your settings](#save)
- [11. See what your sound is doing](#analysis)
- [12. Troubleshooting](#help)
- [13. Before playing and when finished](#checklist)

<a id="prepare"></a>
## 1. Get ready

### What you need

- A computer and the application folder.
- A webcam. A camera built into your computer also works.
- Headphones or speakers, and an audio interface if needed.
- **Python** and **SuperCollider** installed on the computer. SuperCollider produces the sound.
- An internet connection to download the required components during initial setup.

The app currently uses a **Setup** file to prepare it and a **Launch** file to open it, rather than a standalone installer. Setup does not install Python or SuperCollider themselves. If these are missing, ask the person who supplied the app or helps you with setup to prepare the computer first.

The tested environment is Windows with Python 3.10.8 and SuperCollider 3.14.1. Files for macOS are included, but testing on a physical Mac is not yet complete.

### First-time setup

1. If the app came as a ZIP file, extract it into a folder where you can save files.
2. Connect your camera and audio devices.
3. Double-click the Setup file for your operating system.

   | OS | Initial setup | Everyday use |
   | --- | --- | --- |
   | Windows | **Setup Windows.cmd** | **Launch Windows.cmd** |
   | macOS | **Setup macOS.command** | **Launch macOS.command** |

4. When **Setup complete** appears, follow the instructions to close the window.

You do not need to run Setup every time. Run it again if the app's supplier asks you to do so after an update. If a macOS file will not open, pass the displayed message to the person helping with setup.

### Make your hands easy to see

Sit in a well-lit place with both hands and all fingertips visible in the camera image. Keep your hands apart and move slowly at first. Close meeting apps or other programs that are using the camera.

<a id="launch"></a>
## 2. Launch and choose your audio output

1. Double-click the **Launch** file for your operating system.
2. Open **Audio Setup** at the top of the window. You can also find it in each panel's **…** menu.
3. To play only the app's instrument, start with these settings:

   | Setting | Initial choice | What it does |
   | --- | --- | --- |
   | Input (stereo 1 / 2) | **None (internal instrument only)** | Does not bring in external audio |
   | Output (stereo 1 / 2) | **System default**, or your preferred device | Chooses where your speakers or headphones receive the sound |
   | Sample Rate | **SC / hardware default** | Uses the default audio configuration |

4. Press **Apply / Restart SC** and wait for **Audio ready**.
5. Press **Close** to leave the settings window.
6. Set your speakers or headphones to a low volume, then press **Start / F5**.
7. When an image appears in **Camera**, bring both hands into view.

Your audio device settings are reused next time. If you change devices, select them again in Audio Setup and press Apply. Applying settings stops playback and the camera, so press Start again when audio is ready.

**Language connected** means the app has connected to the software that produces sound. Also check for **Audio ready**, which confirms that audio is prepared. Pressing Start before the initial audio setup is complete opens Audio Setup.

<a id="play"></a>
## 3. Play with your hands

### Basic gestures

| Hand or finger | Movement | Result |
| --- | --- | --- |
| Right index finger | Move up / down | Raises / lowers the pitch |
| Left thumb and index finger | Move the tips apart / together | Increases / decreases the volume |
| Right middle finger | Raise its tip above the index fingertip | Raises the pitch by one octave |
| Right middle finger | Move its tip back below the index fingertip | Returns to the original pitch range |

Check the **Left / Right** indicators to make sure the app recognizes each hand correctly. These labels identify the detected hand, rather than its position on the left or right of the image.

Finger spacing is measured in the camera image. Moving closer to or farther from the camera can change the volume even if you keep your fingers the same distance apart. With the default settings, closing your fingers may not silence the sound completely. Use Stop or PANIC to mute it reliably.

### Your first exercise

1. Hold your left thumb and index finger slightly apart and keep them steady.
2. Keep your right middle fingertip below your index fingertip, then slowly move your index finger up and down.
3. Hold your right hand still. Open and close your left thumb and index finger to hear the volume change.
4. Raise and lower your right middle finger to try the octave change.

### Start, stop, and mute

| Button | Key | What it does |
| --- | --- | --- |
| **Start** | **F5** | Starts or resumes playing |
| **Stop** | **F6** | Silences the sound and stops the camera |
| **PANIC** | **F12** | Immediately silences all output, including effect tails and external input, while leaving a running camera active |

Press **Start** to resume after PANIC. You also need to press Start after recalling a sound, switching the sound source, or changing audio devices. Space is not used to start or stop playback in the main interface.

<a id="panels"></a>
## 4. Find and arrange the panels

| Panel | Main purpose |
| --- | --- |
| **Camera** | See your hands, check left/right detection, and set the pitch range and scale |
| **Controls** | Choose a sound source and adjust volume, tone, and response to movement |
| **Effects** | Add modulation, distortion, or ambience; assign gestures and keys; adjust external input volume |
| **Analysis** | View sound and settings as graphs and numbers |

Use **Settings** in Camera to show or hide its settings area. Hide it when you want more space for the camera image while playing.

| Arrangement control | How to use it |
| --- | --- |
| **Detach** | Opens a panel as a separate window, which you can also move to another monitor |
| **Dock** | Returns a separate panel to the main window |
| **Pin** | Keeps a window in front of other applications |
| **… → Lock Position** | Locks the position; turn it off before moving the panel again |
| **Panels** | Shows a hidden panel again |
| **Recover Windows** | Brings floating windows back onto the visible screen |

Start, Stop, and PANIC also work in separate panel windows. Save your preferred arrangement as a **Layout**.

<a id="pitch"></a>
## 5. Set the pitch range and scale

Open **Camera → Settings → Right • Pitch Settings**.

| Setting | Meaning and use |
| --- | --- |
| **Min / Max** | The lowest / highest pitch assigned to the height of your right index finger. Choose note names or enter values in Hz. Min must be lower than Max |
| **Root** | The starting note of the scale, from C through B. A # means one semitone higher |
| **Scale** | The set of notes to use; see the table below |
| **Quantize** | ON snaps pitch to the selected scale. OFF lets pitch change continuously with hand height |
| **Guide Mode** | Guide lines on the camera image: simple for broad reference points, chromatic for semitones, or scale for the selected scale |

| Scale option | Notes used |
| --- | --- |
| **chromatic** | Every semitone |
| **major** | Major scale |
| **minor** | Natural minor scale |
| **major-pentatonic** | Five-note major scale |
| **minor-pentatonic** | Five-note minor scale |

The initial settings are **Min 220 Hz / Max 880 Hz, Root A, Scale minor-pentatonic, Quantize OFF, and Guide Mode simple**.

**Pitch practice example:** Set Root to **C**, Scale to **major**, Quantize to **ON**, and Guide Mode to **scale**. Slowly move your right index finger up and down to play notes in the scale. Turn Quantize OFF to return to continuous pitch slides.

Guide Mode only changes the reference lines. Showing scale lines does not turn on pitch correction. The middle-finger octave gesture can also raise the final pitch above Max.

<a id="tone"></a>
## 6. Shape your sound

### Choose a sound source

In **Controls → Probe**, “Probe” means the type of sound source.

| Sound source | Character | First thing to try |
| --- | --- | --- |
| **Basic / Additive Probe** | Starts with a smooth basic tone and adds harmonics to shape the sound | Enable On in Additive, then gradually change Mix or Harmonics |
| **Subtractive Probe** | Starts with a chosen waveform and uses a filter to shape its brightness | Choose Saw, Pulse, or Triangle for Wave in Osc 1 |

Switching the sound source mutes playback. Press **Start** to resume. Each source keeps its own settings.

### Common adjustments

There are many controls, so change one at a time and listen. For sections with an On control, enable it to hear the effect.

| Location or control | What changes |
| --- | --- |
| **Performance / Output → Output Level** | Overall instrument output volume |
| **Amp Min / Amp Max** | The lower and upper volume limits controlled by your left finger spacing. Lower Amp Min if you want less sound when your fingers are closed |
| **Response → Freq Lag** | How quickly pitch follows your right hand. Higher values make changes smoother and slower |
| **Amp Lag** in Basic | Smoothness of volume changes |
| **Amp Attack / Amp Release** in Subtractive | Response time as volume rises / falls |
| **Portamento → On / Time** in Basic | Makes the pitch glide to the next note |
| **Filter → On / Cutoff / Mix** | Shapes brightness. Lower Cutoff reduces high-frequency content; Mix adjusts how much filtering is blended in |
| **Soft Clip** in Basic | Adds distortion |
| **Osc 2 / Source Mix** in Subtractive | Blends in a second waveform, a low tone, and noise |

**Reset Defaults** restores the selected sound source's initial settings. It does not reset the pitch range or shared effects. Save any sound you want to keep as a Patch first. Press Start to resume after resetting.

### Control brightness and note articulation with your left hand (Subtractive)

Enable **Hand Tone → On** to control brightness with the horizontal position of your left index finger. Set the range with Min Cutoff / Max Cutoff, and reverse the direction with Invert. Enable Filter as well to hear the change.

Enable **Articulation → On** to start and release notes by opening and closing your left thumb and index finger. Adjust the response in Camera under **Left • Mapping**.

| Setting | Meaning |
| --- | --- |
| **Threshold** | Finger spacing at which opening your fingers starts a note |
| **Hysteresis** | The gap between the start and release thresholds, helping prevent rapid on/off changes near the boundary |
| **Hand Loss** | How long to wait before releasing input after the left hand is no longer detected, in milliseconds |

The initial start threshold is 0.65 and the release threshold is 0.45. These values represent finger spacing in the image, not centimeters. If opening your fingers does not start a note, lower Threshold and try again.

**Filter Env** changes brightness over the course of a note. To use it, enable **both Articulation and Filter Env**. Attack controls the initial rise, Decay the time to settle, Sustain the held amount, Release the ending, and Amount the depth of the change.

<a id="effects"></a>
## 7. Use effects

Open **Effects** and enable **On** for the effect you want. All effects are initially OFF. Start with **Input = Manual** while adjusting the controls.

| Effect | What you hear | Main controls |
| --- | --- | --- |
| **Tremolo** | Repeated changes in volume | Rate = speed; Depth = amount of variation |
| **Vibrato** | Repeated changes in pitch | Rate = speed; Depth = pitch variation in ct (cents; 100 ct equals one semitone) |
| **Distortion** | A distorted tone | Drive = distortion; Tone = brightness; Level = volume; Mix = blend |
| **Fuzz** | Strong distortion | Drive, Tone, Level, Mix |
| **Delay** | Repeating echoes | Time = interval; Feedback = amount fed back for further repeats; Mix = blend |
| **Reverb** | The impression of sound in a room or space | Room = space size; Damp = reduction of high frequencies in the reverb; Mix = blend |

For Tremolo and Vibrato, **Wave** offers Sine for smooth movement, Triangle for a steady rise and fall, and Square for distinct switching. **Rate (Hz)** and **Period (ms)** describe the same speed in different units; changing one updates the other.

### First adjustments to try

1. Set Reverb's Input to **Manual** and enable On.
2. Gradually raise Mix from a low value and listen to the added ambience.
3. Turn Reverb OFF, then turn Vibrato On.
4. Change Rate and Depth a little at a time to find a movement you like.

Turning Delay or Reverb OFF leaves existing echoes or reverb tails audible. Press PANIC to silence everything immediately.

### Change the effect order

Drag entries in the effect order list, or select one and press **Earlier / Later**. Changing the order can change the sound. Vibrato changes the source pitch directly, so it is not part of this list.

Changing the order resets any accumulated Delay and Reverb tails.

<a id="gestures"></a>
## 8. Control effects with gestures or keys

Each effect can use its own hand and gesture. Your left hand continues to control volume, and your right hand continues to control pitch at the same time.

### Use finger spacing

For example, make Reverb stronger as you open your right thumb and index finger.

1. Enable Reverb's On control and set **Mix** to the maximum amount you want.
2. Select **Input → Right pinch width** and **Target → Mix**.
3. Open **Mapping / Key**.
4. Show your right hand to the camera. Hold your fingers at the spacing you want for zero effect, then press **Capture** beside **Zero Width**.
5. Hold them at the spacing you want for maximum effect, then press **Capture** beside **Maximum Width**. Use a different spacing from Zero.
6. Open and close your thumb and index finger, watching **Width** and listening to the change.

Choose **Left pinch width** to use your left hand instead. Width is the distance between the fingertips in the camera image. After capturing the positions, keep your distance from the camera as consistent as possible.

### Use the direction between your fingertips

1. For the effect's **Input**, choose **Left pinch angle** or **Right pinch angle**.
2. Choose the control to move under **Target**, and set that control's manual value to the maximum you want.
3. Open **Mapping / Key**.
4. Keep your thumb and index finger apart. Hold them in the direction you want for zero effect, then press **Capture** beside **Zero Direction**.
5. Turn to a different direction for maximum effect, then press **Capture** beside **Maximum Direction**.
6. Change the direction of the line between your fingertips, watching **Angle** and listening to the change.

The angle follows the line from your thumb tip to your index fingertip in the mirrored image. Right is 0° and up is +90°. Keep the tips slightly apart, since overlapping fingertips make the direction difficult to detect.

### Adjust the response

| Setting | When to use it |
| --- | --- |
| **Smoothing** | Smooths the response. Higher values reduce jitter but respond more slowly |
| **Zero Threshold** | Keeps small movements near zero from applying the effect |
| **Invert** | Reverses the response |
| **Response Curve** | Linear increases evenly; Slow starts gradually; Fast increases more strongly at the beginning |
| **Curve Bend** | Adjusts the strength of the Slow or Fast curve |
| **Angle Deadband** | Ignores small angle changes |
| **Minimum Separation** | Treats angle input as invalid when the fingertips are too close together |
| **Direction** | Chooses the angle's travel direction: Shortest, Clockwise, or Counterclockwise |
| **Fold to 180° orientation** | Treats opposite directions as the same line orientation |

When the selected hand is out of view or its input cannot be determined, the effect smoothly returns toward zero. If hand movement has no effect, check **On, Input, Target, and the manual value that sets the maximum**. Select **Manual** under Input to return to manual control.

### Switch effects on and off with keys

1. Open **Mapping / Key** for the effect.
2. Select the **On / Off Key** field and press the key or key combination you want to assign.
3. Choose **Toggle** to switch on/off with each press, or **Hold** to enable the effect only while the key is held.

You cannot assign F5, F6, F12, or a key already assigned to another effect. Shortcuts are suppressed while entering text or numbers. Hold is released when the window or app loses focus.

<a id="thru"></a>
## 9. Play external audio alongside the instrument

You can play incoming stereo audio from another source, such as Koala, alongside the instrument controlled by your hands.

1. Connect the external source and audio input device.
2. In **Audio Setup**, choose the device receiving that sound under Input. The app uses input channels 1 and 2.
3. Choose Output and press **Apply / Restart SC**.
4. Wait for **Audio ready**, then press **Start**.
5. In **Effects → Dry input**, turn **Thru** ON.
6. Adjust the adjacent **Level**, starting low.

External input does not pass through the app's six instrument effects. Use Thru's Level to adjust its volume. PANIC silences both the instrument and external input.

Thru does not turn on automatically at launch, after recalling a Patch, or after reconfiguring audio. Turn it on when needed. It is unavailable when Input is None.

On Windows, if the input/output combination produces a warning, choose devices with compatible audio system prefixes in their names. On macOS, when using separate input and output devices, match their sample rates in the system's Audio MIDI Setup. The iPad / Koala and UR44C combination has not been tested on physical hardware.

<a id="save"></a>
## 10. Save and recall your settings

**Save sound settings as a Patch, and screen arrangements as a Layout.**

| Save type | What it includes |
| --- | --- |
| **Patch** | Both sound sources' settings, pitch range and scale, hand mappings, effects, keys, and effect order |
| **Layout** | Panel positions, sizes, visibility, floating windows, Pin, position locks, and expanded or collapsed settings areas |

### Save a sound

1. Press **Save** in the **Patch** area at the top of the window.
2. The first time, choose a descriptive name such as “Practice” or “Slow tone.”
3. To keep the existing sound and save a new version, use **Save ▾ → Save As…**.

A `*` beside the name means there are unsaved changes. Save anything you want to keep before recalling another sound or closing the app.

### Use a saved sound

1. Select its name from the **Patch** list.
2. Press **Recall**.
3. Recalling mutes playback, so press **Start** to resume playing.

Simply closing the app does not automatically restore your sound changes next time. Save the Patch and recall it after launching the app to use it again.

### Save a screen arrangement

Arrange the panels, then use **Layout → Save** and give the layout a name. To restore it, select it from the Layout list and press **Recall**. This does not change your sound. Separately from named Layouts, the app also restores your last arrangement at the next launch.

Audio device choices and Thru Level are saved separately as settings for this computer. Recalling a Patch does not switch your audio devices.

To make a backup, close the app and copy the **user_data** folder inside the application folder. Patches are in **patches**, and Layouts are in **layouts** within it.

<a id="analysis"></a>
## 11. See what your sound is doing

Open **Analysis** when you need it. You do not need to understand the numbers to play.

- **Open Scope (SC signal)** displays the actual audio waveform in a separate window.
- **Open FreqScope (SC signal)** displays the frequency content of the actual audio.
- **Filter / Envelope / LFO diagrams** illustrate the effect calculated from your settings. They are not recordings or measured waveforms.

If live values are not updating, check that audio is ready and **Controls → Monitor → On** is enabled. Panel Pin settings do not apply to the separate Scope windows.

<a id="help"></a>
## 12. Troubleshooting

If the sound is too loud or will not stop, press **PANIC / F12** first.

| Problem | What to try |
| --- | --- |
| Setup fails | Check that Python is ready. Save the log that opens automatically and share it with the person helping with setup |
| Launch does not open the app | Check that initial Setup completed. If the launch error offers to open a log, open it and share it with your setup helper |
| An audio device is missing or shows Unavailable | Check its connection and press Refresh Devices in Audio Setup. Select an available device and press Apply |
| Apply is unavailable | Wait for the device list to load. If an Unavailable device is selected, choose another device |
| Language connected appears, but there is no sound | Choose your output in Audio Setup and press Apply / Restart SC. Wait for Audio ready, then press Start |
| Start pending stays on screen, or no camera image appears | Check that Audio Setup is complete. Close other camera apps and check the camera connection and operating system permissions. Record any Camera error message |
| The wrong camera appears | There is currently no camera selector in the interface. Ask your setup helper to change the camera specified at launch |
| There is a camera image but no sound | Press Start. Check hand recognition, left finger spacing, Output Level, Amp Min / Amp Max, system volume, and output device. If using Articulation, also check Threshold |
| A quiet sound remains with fingers closed | Lower Amp Min. Press Stop or PANIC to silence the sound reliably |
| Pitch suddenly jumps up an octave | Check whether your right middle fingertip has moved above your index fingertip |
| Pitch changes in steps | Turn Quantize OFF in Camera if you want continuous pitch changes |
| Values jump when you move your hands | Keep hands separate and fingertips visible. Check lighting and hand recognition, and keep a consistent distance from the camera |
| Hand movement does not change an effect | Check On, the hand selected under Input, Target, the manual maximum value, and the captured Zero / Maximum settings |
| Capture does not work | Select the intended hand's angle or width under Input. Press Start, show that hand, and wait for an Angle or Width reading before capturing |
| Angle control is unstable | Separate your fingertips slightly. Increase Smoothing or Angle Deadband. Capture Zero / Maximum again |
| An effect key does not respond | Check that the app has focus and you are not entering text or numbers. Check the key assignment and Toggle / Hold mode |
| External audio cannot be heard | Choose an Input other than None, press Apply, then Start. Check the external source's output, input channels 1 and 2, Thru, and Level |
| A panel is missing | Show it through Panels. Use Recover Windows after disconnecting another monitor or if a floating window is out of view |
| Your previous sound is not restored | Select the saved Patch and press Recall, then Start. Sound settings are not saved automatically |

### What to include when asking for help

Collect the following details to make the problem easier to understand:

- Your operating system, camera, and audio device names.
- The action you took immediately before the problem occurred.
- The error message or a screenshot of it.
- The log opened by **Audio Setup → Open SC Log**. For launch problems, use the **regular-ui-date-and-time.log** file in the application's **logs** folder; the actual filename contains date and time numbers.

Setup logs are also in logs: **setup-windows.log** on Windows or **setup-macos.log** on macOS. You do not need to edit them.

<a id="checklist"></a>
## 13. Before playing and when finished

### Before playing

1. Connect your camera and audio devices.
2. Open the app with the Launch file.
3. Check the output in Audio Setup if needed.
4. Recall a Patch if you want to use a saved sound.
5. Start at a low listening volume, press Start, and check that both hands are recognized.
6. Turn Thru ON if you are using an external source.

### When finished

1. Press **Stop / F6**.
2. Save any sound you want to keep with **Patch → Save**.
3. Use **Layout → Save** if you want to keep a named screen arrangement.
4. Close the main window.

The audio software started automatically by the app also closes.

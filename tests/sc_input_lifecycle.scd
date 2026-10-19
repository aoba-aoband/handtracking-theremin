// Run with sclang tests/sc_input_lifecycle.scd. No camera or audio server needed.
(
var root, basic, subtractive, check, extract;
root = thisProcess.nowExecutingPath.absolutePath.dirname.dirname;
// Keep this test process from rewriting the user's SuperCollider archive.
Archive.global = Archive.new;
Archive.archiveDir = root +/+ "analysis/sc-tests";
File.mkdir(Archive.archiveDir);
SystemClock.sched(8, { "FAIL: lifecycle test timed out".postln; 1.exit; });
basic = File.readAllString(root +/+ "sc/basic_receiver.scd");
subtractive = File.readAllString(root +/+ "sc/subtractive_probe.scd");
check = { |condition, message|
    condition.not.if({ message.postln; 1.exit; });
};
extract = { |source, start, end|
    var offset;
    offset = source.find(start);
    source.copyRange(offset, source.find(end, offset: offset) - 1);
};
[basic, subtractive].do({ |source|
    check.(source.compile.notNil, "Full probe compilation failed");
    // Build actual UGen graphs without booting an audio device.
    (extract.(source, "SynthDef(", "}).add;") ++ "}).add;").interpret;
});

~probeParams = (ampMin: 0.02, ampMax: 0.2);
~probeMonitor = ();
~basicReceiverSynth = nil;
~updateProbeMonitor = {};
~debugSampleEvents = false;
(extract.(basic, "OSCdef(\\sampleLeftPinch", "// Shared, intentionally small")).interpret;

~subtractiveParams = (ampMin: 0.01, ampMax: 0.2, articulationGate: 1);
~subtractiveMonitor = ();
~subtractiveSynth = nil;
~subtractiveDebugEvents = false;
~updateSubtractiveMonitor = {};
~updateSubtractiveHandToneCutoff = {};
~setSubtractiveParam = { |key, value| ~subtractiveParams[key] = value; };
(extract.(subtractive, "OSCdef(\\subtractiveProbeLeftPinch", "// Shared, intentionally small")).interpret;

Routine({
    OSCdef(\sampleLeftPinch).func.value(['/sample/left/pinch', 0.8]);
    OSCdef(\subtractiveProbeLeftPinch).func.value(['/sample/left/pinch', 0.8]);
    check.(~probeMonitor[\targetAmp] > 0, "Basic did not receive amp");
    check.(~subtractiveMonitor[\targetAmp] > 0, "Subtractive did not receive amp");
    1.3.wait;
    check.(~probeMonitor[\targetAmp] == 0, "Basic timeout did not mute");
    check.(~subtractiveMonitor[\targetAmp] == 0, "Subtractive timeout did not mute");
    check.(~subtractiveParams[\articulationGate] == 0, "Timeout did not release articulation");
    OSCdef(\sampleLeftPinch).func.value(['/sample/left/pinch', 0.8]);
    OSCdef(\subtractiveProbeLeftPinch).func.value(['/sample/left/pinch', 0.8]);
    check.(~probeMonitor[\targetAmp] > 0, "Basic failed to resume");
    check.(~subtractiveMonitor[\targetAmp] > 0, "Subtractive failed to resume");
    OSCdef(\basicProbePanic).func.value(['/sample/panic', 1]);
    OSCdef(\subtractiveProbePanic).func.value(['/sample/panic', 1]);
    check.(~probeMonitor[\targetAmp] == 0, "Basic panic did not mute");
    check.(~subtractiveMonitor[\targetAmp] == 0, "Subtractive panic did not mute");
    ~basicInputWatchdog.stop;
    ~subtractiveInputWatchdog.stop;
    OSCdef.freeAll;
    "PASS: probe compilation, SynthDefs, watchdog, resume, panic".postln;
    0.exit;
}).play(SystemClock);
)

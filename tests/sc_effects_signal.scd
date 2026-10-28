// Offline audio render: real production SynthDefs, no physical audio output.
(
var root, output, extract, definitions, render, pending;
root = thisProcess.nowExecutingPath.absolutePath.dirname.dirname;
output = root +/+ "analysis/effects-signal";
Archive.global = Archive.new; Archive.archiveDir = output;
extract = { |source| var start; start = source.find("SynthDef("); source.copyRange(start, source.find("}).add;", offset: start) + 6); };
(root +/+ "sc/regular_effect_specs.scd").load;
(root +/+ "sc/regular_engine.scd").load;
~regularDefineDSP.();
~regularUIOnly = true;
extract.(File.readAllString(root +/+ "sc/basic_receiver.scd")).interpret;
extract.(File.readAllString(root +/+ "sc/subtractive_probe.scd")).interpret;
SynthDef(\regularTestTone, { |out=16, amp=0.1, freq=440|
    Out.ar(out, SinOsc.ar(freq) * amp ! 2);
}).add;
definitions = [\basicOscProbe, \subtractiveProbe, \regularTestTone, \regularTremolo, \regularDistortion, \regularFuzz, \regularDelay, \regularReverb, \regularThru, \regularMaster];
render = { |name, complete|
    var score, options, tone, distortion, fuzz, delay, reverb, tremolo, vibrato;
    options = ServerOptions.new.numInputBusChannels_(2).numOutputBusChannels_(2).memSize_(32768);
    score = List.new;
    definitions.do({ |def| score.add([0.0, ['/d_recv', SynthDescLib.global.at(def).def.asBytes]]); });
    score.add([0.0, ['/b_alloc', 0, 131072, 1], ['/b_alloc', 1, 131072, 1]]);
    tone = (name != "thru").asInteger;
    distortion = ["distortion", "distortion_high", "thru", "internal"].includesEqual(name).asInteger;
    fuzz = ["fuzz", "fuzz_high", "thru"].includesEqual(name).asInteger;
    delay = ["delay_tail", "thru", "internal"].includesEqual(name).asInteger;
    reverb = ["reverb_tail", "thru", "internal"].includesEqual(name).asInteger;
    tremolo = ["tremolo", "thru"].includesEqual(name).asInteger;
    vibrato = (name == "vibrato").asInteger;
    score.add([0.01, ['/s_new', (name == "subtractive").if({ \subtractiveProbe }, { (vibrato == 1).if({ \basicOscProbe }, { \regularTestTone }) }), 10, 1, 1,
        \out, 16, \amp, 0.1 * tone, \freq, name.endsWith("_high").if({ 5000 }, { 440 }), \freqLag, 0, \ampLag, 0,
        \performanceGate, 1, \crescendoTime, 0, \outputLevel, 1, \sharedFX, 1,
        \vibratoOn, vibrato, \vibratoRate, 5, \vibratoDepth, 40, \vibratoWave, 0]]);
    score.add([0.01, ['/s_new', \regularTremolo, 20, 1, 1, \in, 16, \out, 18, \on, tremolo, \rate, 6, \depth, 0.6]]);
    score.add([0.01, ['/s_new', \regularDistortion, 21, 1, 1, \in, 18, \out, 20, \on, distortion, \drive, 8, \tone, 8000, \level, 1]]);
    score.add([0.01, ['/s_new', \regularFuzz, 22, 1, 1, \in, 20, \out, 22, \on, fuzz, \drive, 8, \tone, 8000, \level, 1]]);
    score.add([0.01, ['/s_new', \regularDelay, 23, 1, 1, \in, 22, \out, 24, \on, delay, \mix, 0.7, \time, 0.2, \feedback, 0.4]]);
    score.add([0.01, ['/s_new', \regularReverb, 24, 1, 1, \in, 24, \out, 26, \on, reverb, \mix, 0.7, \room, 0.7]]);
    score.add([0.01, ['/s_new', \regularThru, 30, 1, 1, \out, 30, \on, (name == "thru").asInteger, \level, 1]]);
    score.add([0.01, ['/s_new', \regularMaster, 40, 1, 1, \inA, 26, \inB, 26, \thru, 30, \mute, 0]]);
    name.endsWith("_high").if({ score.add([0.02, ['/n_set', 21, \drive, 30], ['/n_set', 22, \drive, 40]]); });
    (["delay_tail", "reverb_tail"].includesEqual(name)).if({
        score.add([0.5, ['/n_set', 10, \amp, 0], ['/n_set', 23, \on, 0], ['/n_set', 24, \on, 0]]);
    });
    (name == "thru").if({
        score.add([0.7, ['/n_set', 20, \depth, 1], ['/n_set', 21, \drive, 35], ['/n_set', 22, \drive, 60], ['/n_set', 23, \time, 0.1]]);
    });
    score.add([2.0, ['/n_set', 40, \mute, 1]]);
    score.add([2.1, ['/g_freeAll', 1]]);
    score.add([2.2, ['/b_free', 0], ['/b_free', 1]]);
    score.add([2.5, ['/c_set', 0, 0]]);
    Score(score.asArray).recordNRT(
        oscFilePath: output +/+ (name ++ ".osc"), outputFilePath: output +/+ (name ++ ".wav"),
        inputFilePath: output +/+ "input.wav", sampleRate: 48000, headerFormat: "WAV", sampleFormat: "int16",
        options: options, duration: 2.5, action: { |code| complete.value(code); });
};
pending = ["thru", "internal", "distortion", "fuzz", "delay_tail", "reverb_tail", "vibrato", "tremolo", "subtractive", "distortion_high", "fuzz_high"];
Routine({
    pending.do({ |name|
        var done, exitCode, count;
        done = false; count = 0;
        render.(name, { |code| exitCode = code; done = true; });
        while { done.not and: { count < 600 } } { 0.05.wait; count = count + 1; };
        ((done == false) or: { exitCode != 0 }).if({ ("FAIL render: " ++ name ++ " exit=" ++ exitCode.asString).postln; 1.exit; });
    });
    "PASS: offline production FX/Thru/PANIC renders".postln; 0.exit;
}).play(SystemClock);
)

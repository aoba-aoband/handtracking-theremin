/*
Subtractive synthesis probe for the Handtracking Theremin sample mapping.

This is intentionally separate from basic_receiver.scd. Python decides pitch,
quantization, and final_freq; this file decides how that received frequency is
followed, voiced, filtered, and brought into a performance.
*/

(
var subtractiveProbeInstance;

// A probe owns the sample-mapping OSC handlers while it is active.  Evaluating
// either probe first runs the previous probe's cleanup, preventing double sound.
~activeProbeCleanup.notNil.if({
    ~activeProbeCleanup.();
});
~activeProbeCleanup = nil;
// Invalidate a basic-receiver evaluation that may still be waiting for boot.
~basicProbeInstance = (~basicProbeInstance ? 0) + 1;
subtractiveProbeInstance = (~subtractiveProbeInstance ? 0) + 1;
~subtractiveProbeInstance = subtractiveProbeInstance;

s.waitForBoot({
    (~subtractiveProbeInstance == subtractiveProbeInstance).if({
        ~subtractiveDebugEvents = false;

        ~subtractiveDefaults = (
            freqLag: 0.08,
            ampAttack: 0.05,
            ampRelease: 0.12,
            articulationOn: 0,
            articulationGate: 0,
            articulationAttack: 0.02,
            articulationRelease: 0.08,
            performanceGate: 0,
            crescendoTime: 1.5,
            decrescendoTime: 1.5,
            outputLevel: 0.35,
            ampMin: 0.01,
            ampMax: 0.16,
            osc1Wave: 0,
            osc2On: 0,
            osc2Wave: 0,
            osc2Octave: 0,
            osc2DetuneCents: 0,
            oscMix: 0.0,
            pulseWidth: 0.5,
            subMix: 0.0,
            noiseMix: 0.0,
            filterOn: 1,
            filterCutoff: 2400,
            filterRq: 0.7,
            filterMix: 1.0,
            filterLag: 0.08,
            filterEnvOn: 0,
            filterEnvAttack: 0.01,
            filterEnvDecay: 0.18,
            filterEnvSustain: 0.35,
            filterEnvRelease: 0.15,
            filterEnvAmountOctaves: 1.5,
            keyTracking: 0.35,
            handToneOn: 0,
            toneMinCutoff: 160,
            toneMaxCutoff: 8000,
            toneInvert: 0,
            handToneCutoff: 2400,
            monitorOn: 1,
            monitorRate: 8
        );
        ~subtractiveParams = ~subtractiveDefaults.copy;
        ~subtractiveSynthParamKeys = [
            \freqLag,
            \ampAttack,
            \ampRelease,
            \articulationOn,
            \articulationGate,
            \articulationAttack,
            \articulationRelease,
            \performanceGate,
            \crescendoTime,
            \decrescendoTime,
            \outputLevel,
            \osc1Wave,
            \osc2On,
            \osc2Wave,
            \osc2Octave,
            \osc2DetuneCents,
            \oscMix,
            \pulseWidth,
            \subMix,
            \noiseMix,
            \filterOn,
            \filterCutoff,
            \filterRq,
            \filterMix,
            \filterLag,
            \filterEnvOn,
            \filterEnvAttack,
            \filterEnvDecay,
            \filterEnvSustain,
            \filterEnvRelease,
            \filterEnvAmountOctaves,
            \keyTracking,
            \handToneOn,
            \handToneCutoff,
            \monitorOn,
            \monitorRate
        ];
        ~subtractiveMonitor = (
            targetFreq: 440.0,
            targetAmp: 0.05,
            followedFreq: 440.0,
            followedAmp: 0.05,
            articulationEnv: 1.0,
            filterEnvValue: 0.0,
            filterEnvMultiplier: 1.0,
            performanceEnv: 0.0,
            targetToneNorm: 0.0,
            mappedHandToneCutoff: 2400.0,
            manualFilterCutoff: 2400.0,
            effectiveCutoff: 2400.0
        );

        SynthDef(\subtractiveProbe, { |out = 0, freq = 440, amp = 0.05, uiMute = 0, sharedFX = 0,
        vibratoOn = 0, vibratoRate = 5, vibratoDepth = 0, vibratoWave = 0, monitorBus = 0, monitorGeneration = 0,
            freqLag = 0.08, ampAttack = 0.05, ampRelease = 0.12,
            articulationOn = 0, articulationGate = 0,
            articulationAttack = 0.02, articulationRelease = 0.08,
            performanceGate = 0, crescendoTime = 1.5, decrescendoTime = 1.5,
            outputLevel = 0.35,
            osc1Wave = 0, osc2On = 0, osc2Wave = 0, osc2Octave = 0,
            osc2DetuneCents = 0, oscMix = 0, pulseWidth = 0.5,
            subMix = 0, noiseMix = 0,
            filterOn = 1, filterCutoff = 2400, filterRq = 0.7,
            filterMix = 1, filterLag = 0.08, keyTracking = 0.35,
            filterEnvOn = 0, filterEnvAttack = 0.01,
            filterEnvDecay = 0.18, filterEnvSustain = 0.35,
            filterEnvRelease = 0.15, filterEnvAmountOctaves = 1.5,
            handToneOn = 0, handToneCutoff = 2400,
            monitorOn = 1, monitorRate = 8|

            var followedFreq, followedAmp, performanceEnv, oscFreq, vibratoLFO;
            var articulationActive, clippedArticulationGate, articulationEnv;
            var width, osc1, osc2Freq, osc2, osc2Blend, oscillatorMix;
            var sub, noise, sourceMix, sourceDenom;
            var baseCutoff, trackedCutoff, smoothedBaseCutoff, effectiveCutoff;
            var filterEnvActive, filterEnvValue, filterEnvMultiplier;
            var filtered, filterBlend, postFilter;
            var afterAmp, afterArticulation, afterGate, sig, monitorTrig;

            followedFreq = Lag.kr(freq.clip(20, 20000), freqLag.max(0));
            followedAmp = LagUD.kr(
                amp.max(0),
                ampAttack.max(0.001),
                ampRelease.max(0.001)
            );
            performanceEnv = LagUD.kr(
                performanceGate.clip(0, 1),
                crescendoTime.max(0.001),
                decrescendoTime.max(0.001)
            );
            articulationActive = articulationOn.clip(0, 1);
            clippedArticulationGate = articulationGate.clip(0, 1);
            articulationEnv = Select.kr(articulationActive, [
                1.0,
                EnvGen.kr(
                    Env.asr(
                        articulationAttack.max(0.001),
                        1.0,
                        articulationRelease.max(0.001),
                        curve: -4
                    ),
                    clippedArticulationGate,
                    doneAction: 0
                )
            ]);
            width = pulseWidth.clip(0.05, 0.95);

            vibratoLFO = Lag.kr(Select.kr(vibratoWave.clip(0, 2), [SinOsc.kr(Lag.kr(vibratoRate, 0.03)), LFTri.kr(Lag.kr(vibratoRate, 0.03)), LFPulse.kr(Lag.kr(vibratoRate, 0.03)).range(-1, 1)]), 0.003);
            oscFreq = followedFreq * (2 ** (vibratoLFO * Lag.kr(vibratoOn * vibratoDepth, 0.03) / 1200));
            // oscillator source: 0 = Saw, 1 = Pulse, 2 = Triangle
            osc1 = Select.ar(osc1Wave.clip(0, 2), [
                Saw.ar(oscFreq),
                Pulse.ar(oscFreq, width),
                LFTri.ar(oscFreq)
            ]);
            osc2Freq = oscFreq
                * (2 ** osc2Octave.clip(-2, 2))
                * (2 ** (osc2DetuneCents.clip(-50, 50) / 1200));
            osc2 = Select.ar(osc2Wave.clip(0, 2), [
                Saw.ar(osc2Freq),
                Pulse.ar(osc2Freq, width),
                LFTri.ar(osc2Freq)
            ]);
            osc2Blend = osc2On.clip(0, 1) * oscMix.clip(0, 1);
            oscillatorMix = SelectX.ar(osc2Blend, [osc1, osc2]);

            sub = SinOsc.ar(oscFreq * 0.5);
            noise = PinkNoise.ar;
            // source mix: normalize optional sub/noise so their mix changes
            // remain controlled before the resonant filter.
            sourceDenom = (1 + subMix.clip(0, 1) + noiseMix.clip(0, 1)).max(1);
            sourceMix = (
                oscillatorMix
                + (sub * subMix.clip(0, 1))
                + (noise * noiseMix.clip(0, 1))
            ) / sourceDenom;

            // handToneOn selects either the V1 manual cutoff or the cutoff
            // mapped from left-hand tone norm before keyTracking is applied.
            baseCutoff = Select.kr(handToneOn.clip(0, 1), [
                filterCutoff.clip(40, 16000),
                handToneCutoff.clip(40, 16000)
            ]);
            // keyTracking raises the selected base cutoff for higher notes so
            // their relative brightness can stay more consistent. At 0 it is fixed.
            trackedCutoff = baseCutoff
                * ((followedFreq / 440).clip(0.125, 8) ** keyTracking.clip(0, 1));
            smoothedBaseCutoff = Lag.kr(
                trackedCutoff.clip(40, 16000),
                filterLag.max(0)
            );
            filterEnvValue = EnvGen.kr(
                Env.adsr(
                    filterEnvAttack.max(0.001),
                    filterEnvDecay.max(0.001),
                    filterEnvSustain.clip(0, 1),
                    filterEnvRelease.max(0.001),
                    peakLevel: 1.0,
                    curve: -4
                ),
                clippedArticulationGate,
                doneAction: 0
            );
            filterEnvActive = filterEnvOn.clip(0, 1) * articulationActive;
            filterEnvMultiplier = Select.kr(filterEnvActive, [
                1.0,
                2 ** (filterEnvValue * filterEnvAmountOctaves.clip(0, 5))
            ]);
            effectiveCutoff = (smoothedBaseCutoff * filterEnvMultiplier).clip(40, 18000);
            filtered = RLPF.ar(
                sourceMix,
                effectiveCutoff,
                filterRq.clip(0.05, 1.0)
            );
            // filterOn OFF always selects dry source, regardless of filterMix.
            filterBlend = filterOn.clip(0, 1) * filterMix.clip(0, 1);
            postFilter = SelectX.ar(filterBlend, [sourceMix, filtered]);

            // Signal path:
            // oscillators / sub / noise -> source mix -> RLPF
            // -> followed pinch amp -> articulation amp envelope
            // -> performance gate -> LeakDC / Limiter -> stereo Out.
            // Filter cutoff:
            // manual or hand-tone cutoff -> key tracking -> filter lag
            // -> optional filter envelope -> RLPF cutoff.
            afterAmp = postFilter * followedAmp;
            afterArticulation = afterAmp * articulationEnv;
            afterGate = afterArticulation
                * performanceEnv
                * outputLevel.clip(0, 0.8);
            sig = LeakDC.ar(afterGate ! 2);
            sig = (~regularUIOnly == true).if({ sig.clip2(0.8) }, { Limiter.ar(sig, 0.8, 0.01) });

            monitorTrig = Impulse.kr(monitorRate.clip(0.5, 20)) * monitorOn.clip(0, 1);
            (~regularUIOnly == true).if({
                Out.kr(monitorBus, [monitorGeneration] ++ [
                    freq,
                    amp,
                    followedFreq,
                    followedAmp,
                    performanceEnv,
                    articulationActive,
                    clippedArticulationGate,
                    articulationEnv,
                    filterEnvOn.clip(0, 1),
                    filterEnvValue,
                    filterEnvAmountOctaves.clip(0, 5),
                    filterEnvMultiplier,
                    filterCutoff,
                    handToneCutoff,
                    effectiveCutoff,
                    oscFreq
                ]);
            }, {
            SendReply.kr(
                monitorTrig,
                '/subtractiveProbe/monitor',
                [
                    freq,
                    amp,
                    followedFreq,
                    followedAmp,
                    performanceEnv,
                    articulationActive,
                    clippedArticulationGate,
                    articulationEnv,
                    filterEnvOn.clip(0, 1),
                    filterEnvValue,
                    filterEnvAmountOctaves.clip(0, 5),
                    filterEnvMultiplier,
                    filterCutoff,
                    handToneCutoff,
                    effectiveCutoff
                ]
            );
            });

            Out.ar(out, sig * (1 - uiMute.clip(0, 1)));
        }).add;

        s.sync;

        ~subtractiveSynth.notNil.if({
            ~subtractiveSynth.free;
        });
        "creating subtractive probe synth".postln;
        ~subtractiveSynth = Synth(\subtractiveProbe, [
            \freqLag, ~subtractiveParams[\freqLag],
            \ampAttack, ~subtractiveParams[\ampAttack],
            \ampRelease, ~subtractiveParams[\ampRelease],
            \articulationOn, ~subtractiveParams[\articulationOn],
            \articulationGate, ~subtractiveParams[\articulationGate],
            \articulationAttack, ~subtractiveParams[\articulationAttack],
            \articulationRelease, ~subtractiveParams[\articulationRelease],
            \performanceGate, ~subtractiveParams[\performanceGate],
            \crescendoTime, ~subtractiveParams[\crescendoTime],
            \decrescendoTime, ~subtractiveParams[\decrescendoTime],
            \outputLevel, ~subtractiveParams[\outputLevel],
            \osc1Wave, ~subtractiveParams[\osc1Wave],
            \osc2On, ~subtractiveParams[\osc2On],
            \osc2Wave, ~subtractiveParams[\osc2Wave],
            \osc2Octave, ~subtractiveParams[\osc2Octave],
            \osc2DetuneCents, ~subtractiveParams[\osc2DetuneCents],
            \oscMix, ~subtractiveParams[\oscMix],
            \pulseWidth, ~subtractiveParams[\pulseWidth],
            \subMix, ~subtractiveParams[\subMix],
            \noiseMix, ~subtractiveParams[\noiseMix],
            \filterOn, ~subtractiveParams[\filterOn],
            \filterCutoff, ~subtractiveParams[\filterCutoff],
            \filterRq, ~subtractiveParams[\filterRq],
            \filterMix, ~subtractiveParams[\filterMix],
            \filterLag, ~subtractiveParams[\filterLag],
            \filterEnvOn, ~subtractiveParams[\filterEnvOn],
            \filterEnvAttack, ~subtractiveParams[\filterEnvAttack],
            \filterEnvDecay, ~subtractiveParams[\filterEnvDecay],
            \filterEnvSustain, ~subtractiveParams[\filterEnvSustain],
            \filterEnvRelease, ~subtractiveParams[\filterEnvRelease],
            \filterEnvAmountOctaves, ~subtractiveParams[\filterEnvAmountOctaves],
            \keyTracking, ~subtractiveParams[\keyTracking],
            \handToneOn, ~subtractiveParams[\handToneOn],
            \handToneCutoff, ~subtractiveParams[\handToneCutoff],
            \monitorOn, ~subtractiveParams[\monitorOn],
            \monitorRate, ~subtractiveParams[\monitorRate]
        ]);

        ~fmtSubtractiveNumber = { |value, step = 0.001|
            (value ? 0).asFloat.round(step).asString;
        };
        ~fmtSubtractiveHz = { |value|
            ~fmtSubtractiveNumber.(value, 0.1) ++ " Hz";
        };
        ~fmtSubtractiveOnOff = { |value|
            ((value ? 0).asFloat >= 0.5).if({ "ON" }, { "OFF" });
        };
        ~subtractiveWaveName = { |value|
            ["Saw", "Pulse", "Triangle"][value.asInteger.clip(0, 2)];
        };

        ~refreshSubtractiveMonitor = {
            var labels;
            labels = ~subtractiveMonitorLabels;
            labels.notNil.if({
                labels[\freq].notNil.if({
                    labels[\freq].string_(
                        "targetFreq: " ++ ~fmtSubtractiveHz.(~subtractiveMonitor[\targetFreq])
                        ++ "    followedFreq: "
                        ++ ~fmtSubtractiveHz.(~subtractiveMonitor[\followedFreq])
                    );
                });
                labels[\amp].notNil.if({
                    labels[\amp].string_(
                        "targetAmp: "
                        ++ ~fmtSubtractiveNumber.(~subtractiveMonitor[\targetAmp])
                        ++ "    followedAmp: "
                        ++ ~fmtSubtractiveNumber.(~subtractiveMonitor[\followedAmp])
                    );
                });
                labels[\gate].notNil.if({
                    labels[\gate].string_(
                        "performanceGate: "
                        ++ ~fmtSubtractiveOnOff.(~subtractiveParams[\performanceGate])
                        ++ "    envelope: "
                        ++ ~fmtSubtractiveNumber.(~subtractiveMonitor[\performanceEnv], 0.01)
                    );
                });
                labels[\articulation].notNil.if({
                    labels[\articulation].string_(
                        "articulationOn: "
                        ++ ~fmtSubtractiveOnOff.(~subtractiveParams[\articulationOn])
                        ++ "    articulationGate: "
                        ++ ~fmtSubtractiveOnOff.(~subtractiveParams[\articulationGate])
                        ++ "    articulationEnv: "
                        ++ ~fmtSubtractiveNumber.(~subtractiveMonitor[\articulationEnv], 0.01)
                    );
                });
                labels[\filter].notNil.if({
                    labels[\filter].string_(
                        "manualFilterCutoff: "
                        ++ ~fmtSubtractiveHz.(~subtractiveMonitor[\manualFilterCutoff])
                        ++ "    effectiveCutoff: "
                        ++ ~fmtSubtractiveHz.(~subtractiveMonitor[\effectiveCutoff])
                        ++ "    filter " ++ ~fmtSubtractiveOnOff.(~subtractiveParams[\filterOn])
                        ++ "    mix "
                        ++ ~fmtSubtractiveNumber.(~subtractiveParams[\filterMix])
                    );
                });
                labels[\filterEnv].notNil.if({
                    labels[\filterEnv].string_(
                        "filterEnvOn: "
                        ++ ~fmtSubtractiveOnOff.(~subtractiveParams[\filterEnvOn])
                        ++ "    value: "
                        ++ ~fmtSubtractiveNumber.(~subtractiveMonitor[\filterEnvValue], 0.01)
                        ++ "    amountOctaves: "
                        ++ ~fmtSubtractiveNumber.(~subtractiveParams[\filterEnvAmountOctaves], 0.01)
                        ++ "    multiplier: "
                        ++ ~fmtSubtractiveNumber.(~subtractiveMonitor[\filterEnvMultiplier], 0.01)
                    );
                });
                labels[\handTone].notNil.if({
                    labels[\handTone].string_(
                        "handToneOn: "
                        ++ ~fmtSubtractiveOnOff.(~subtractiveParams[\handToneOn])
                        ++ "    targetToneNorm: "
                        ++ ~fmtSubtractiveNumber.(~subtractiveMonitor[\targetToneNorm])
                        ++ "    mappedHandToneCutoff: "
                        ++ ~fmtSubtractiveHz.(~subtractiveMonitor[\mappedHandToneCutoff])
                    );
                });
                labels[\oscillators].notNil.if({
                    labels[\oscillators].string_(
                        "osc1: " ++ ~subtractiveWaveName.(~subtractiveParams[\osc1Wave])
                        ++ "    osc2: "
                        ++ ~fmtSubtractiveOnOff.(~subtractiveParams[\osc2On])
                        ++ " / " ++ ~subtractiveWaveName.(~subtractiveParams[\osc2Wave])
                    );
                });
                labels[\output].notNil.if({
                    labels[\output].string_(
                        "outputLevel: "
                        ++ ~fmtSubtractiveNumber.(~subtractiveParams[\outputLevel])
                        ++ "    amp range: "
                        ++ ~fmtSubtractiveNumber.(~subtractiveParams[\ampMin])
                        ++ " - "
                        ++ ~fmtSubtractiveNumber.(~subtractiveParams[\ampMax])
                    );
                });
            });
        };

        ~updateSubtractiveMonitor = {
            { ~refreshSubtractiveMonitor.(); }.defer;
        };

        ~setSubtractiveParam = { |key, value|
            (key == \articulationGate).if({
                value = value.asFloat.clip(0, 1);
            });
            ~subtractiveParams[key] = value;
            (key == \filterCutoff).if({
                ~subtractiveMonitor[\manualFilterCutoff] = value.asFloat.clip(40, 16000);
            });
            (key == \handToneCutoff).if({
                ~subtractiveMonitor[\mappedHandToneCutoff] = value.asFloat.clip(40, 16000);
            });
            (~subtractiveSynth.notNil and: {
                ~subtractiveSynthParamKeys.includes(key)
            }).if({
                ~subtractiveSynth.set(key, value);
            });
            ~updateSubtractiveMonitor.();
        };

        ~updateSubtractiveHandToneCutoff = { |rawToneNorm|
            var toneNorm, mappedNorm, firstCutoff, secondCutoff;
            var minCutoff, maxCutoff, cutoff;
            toneNorm = rawToneNorm.asFloat.clip(0, 1);
            firstCutoff = (~subtractiveParams[\toneMinCutoff] ? 160).asFloat.clip(40, 16000);
            secondCutoff = (~subtractiveParams[\toneMaxCutoff] ? 8000).asFloat.clip(40, 16000);
            minCutoff = firstCutoff.min(secondCutoff);
            maxCutoff = firstCutoff.max(secondCutoff);
            mappedNorm = ((~subtractiveParams[\toneInvert] ? 0).asFloat >= 0.5).if({
                1.0 - toneNorm;
            }, {
                toneNorm;
            });
            cutoff = (minCutoff == maxCutoff).if({
                minCutoff;
            }, {
                mappedNorm.linexp(0, 1, minCutoff, maxCutoff);
            }).clip(40, 16000);
            ~subtractiveMonitor[\targetToneNorm] = toneNorm;
            ~setSubtractiveParam.(\handToneCutoff, cutoff);
        };

        ~setSubtractiveToneRange = { |key, value|
            var minCutoff, maxCutoff;
            minCutoff = (~subtractiveParams[\toneMinCutoff] ? 160).asFloat.clip(40, 16000);
            maxCutoff = (~subtractiveParams[\toneMaxCutoff] ? 8000).asFloat.clip(40, 16000);
            (key == \toneMinCutoff).if({
                minCutoff = value.asFloat.clip(40, 16000);
                (minCutoff > maxCutoff).if({
                    maxCutoff = minCutoff;
                });
            }, {
                maxCutoff = value.asFloat.clip(40, 16000);
                (maxCutoff < minCutoff).if({
                    minCutoff = maxCutoff;
                });
            });
            ~setSubtractiveParam.(\toneMinCutoff, minCutoff);
            ~setSubtractiveParam.(\toneMaxCutoff, maxCutoff);
            {
                ~subtractiveControls.notNil.if({
                    ~subtractiveControls[\toneMinCutoff].notNil.if({
                        ~subtractiveControls[\toneMinCutoff].value_(minCutoff);
                    });
                    ~subtractiveControls[\toneMaxCutoff].notNil.if({
                        ~subtractiveControls[\toneMaxCutoff].value_(maxCutoff);
                    });
                });
            }.defer;
            ~updateSubtractiveHandToneCutoff.(~subtractiveMonitor[\targetToneNorm] ? 0);
        };

        ~setSubtractiveToneInvert = { |value|
            ~setSubtractiveParam.(\toneInvert, value.clip(0, 1).asInteger);
            ~updateSubtractiveHandToneCutoff.(~subtractiveMonitor[\targetToneNorm] ? 0);
        };

        ~setSubtractivePerformanceGate = { |value|
            var gate;
            gate = value.clip(0, 1).asInteger;
            ~setSubtractiveParam.(\performanceGate, gate);
            {
                ~subtractiveControls.notNil.if({
                    ~subtractiveControls[\performanceGate].notNil.if({
                        ~subtractiveControls[\performanceGate].value_(gate);
                    });
                });
            }.defer;
        };

        ~toggleSubtractivePerformanceGate = {
            var current;
            current = (~subtractiveParams[\performanceGate] ? 0).asInteger;
            ~setSubtractivePerformanceGate.((1 - current).asInteger);
        };

        ~resetSubtractiveParams = {
            ~subtractiveDefaults.keysValuesDo({ |key, value|
                ~setSubtractiveParam.(key, value);
            });
            ~subtractiveMonitor[\targetToneNorm] = 0.0;
            ~subtractiveMonitor[\mappedHandToneCutoff] = ~subtractiveDefaults[\handToneCutoff];
            ~subtractiveMonitor[\manualFilterCutoff] = ~subtractiveDefaults[\filterCutoff];
            ~subtractiveMonitor[\articulationEnv] = 1.0;
            ~subtractiveMonitor[\filterEnvValue] = 0.0;
            ~subtractiveMonitor[\filterEnvMultiplier] = 1.0;
            {
                ~subtractiveControls.notNil.if({
                    ~subtractiveControls.keysValuesDo({ |key, control|
                        control.value_(~subtractiveParams[key]);
                    });
                });
            }.defer;
        };

        ~openSubtractiveScope = {
            {
                try {
                    s.scope(2);
                } { |error|
                    ("Open Scope failed: " ++ error.asString).postln;
                };
            }.defer;
        };

        ~openSubtractiveFreqScope = {
            {
                try {
                    ~subtractiveFreqScope = FreqScope.new;
                } { |error|
                    ("Open FreqScope failed: " ++ error.asString).postln;
                };
            }.defer;
        };

        if(~regularUIOnly != true, { {
            (~subtractiveProbeInstance == subtractiveProbeInstance).if({
                ~subtractiveWindow.notNil.if({
                    ~subtractiveWindow.close;
                });
                ~subtractiveMonitorWindow.notNil.if({
                    ~subtractiveMonitorWindow.close;
                });
                ~subtractiveMonitorLabels = nil;
                ~subtractiveWindow = Window(
                    "Subtractive Probe Controls",
                    Rect(100, 40, 500, 1040)
                );
                ~subtractiveControls = ();

                ~makeSubtractiveSlider = {
                    |label, key, minValue, maxValue, step = 0, warp = \lin|
                    var slider;
                    slider = EZSlider(
                        ~subtractiveWindow,
                        450@22,
                        label,
                        ControlSpec(
                            minValue,
                            maxValue,
                            warp,
                            step,
                            ~subtractiveParams[key]
                        ),
                        { |view| ~setSubtractiveParam.(key, view.value); },
                        ~subtractiveParams[key]
                    );
                    ~subtractiveControls[key] = slider;
                    slider.view;
                };

                ~makeSubtractiveToneRangeSlider = { |label, key|
                    var slider;
                    slider = EZSlider(
                        ~subtractiveWindow,
                        450@22,
                        label,
                        ControlSpec(
                            40.0,
                            16000.0,
                            \exp,
                            1.0,
                            ~subtractiveParams[key]
                        ),
                        { |view| ~setSubtractiveToneRange.(key, view.value); },
                        ~subtractiveParams[key]
                    );
                    ~subtractiveControls[key] = slider;
                    slider.view;
                };

                ~makeSubtractiveToggle = { |label, key|
                    var button;
                    button = Button()
                        .states_([
                            [label ++ ": OFF", Color.black, Color.gray(0.85)],
                            [label ++ ": ON", Color.white, Color(0.2, 0.45, 0.8)]
                        ])
                        .value_(~subtractiveParams[key].asInteger)
                        .action_({ |view| ~setSubtractiveParam.(key, view.value); });
                    ~subtractiveControls[key] = button;
                    button;
                };

                ~makeSubtractiveToneInvertToggle = {
                    var button;
                    button = Button()
                        .states_([
                            ["toneInvert: OFF", Color.black, Color.gray(0.85)],
                            ["toneInvert: ON", Color.white, Color(0.2, 0.45, 0.8)]
                        ])
                        .value_(~subtractiveParams[\toneInvert].asInteger)
                        .action_({ |view| ~setSubtractiveToneInvert.(view.value); });
                    ~subtractiveControls[\toneInvert] = button;
                    button;
                };

                ~makeSubtractiveWaveMenu = { |label, key|
                    var menu;
                    menu = PopUpMenu()
                        .items_(["Saw", "Pulse", "Triangle"])
                        .value_(~subtractiveParams[key].asInteger)
                        .action_({ |view| ~setSubtractiveParam.(key, view.value); });
                    ~subtractiveControls[key] = menu;
                    HLayout(
                        StaticText().string_(label).minWidth_(165),
                        menu
                    );
                };

                ~makeSubtractiveGateButton = {
                    var button;
                    button = Button()
                        .states_([
                            ["Gate: OFF (space)", Color.black, Color.gray(0.85)],
                            ["Gate: ON (space)", Color.white, Color(0.2, 0.6, 0.25)]
                        ])
                        .value_(~subtractiveParams[\performanceGate].asInteger)
                        .action_({ ~toggleSubtractivePerformanceGate.(); });
                    ~subtractiveControls[\performanceGate] = button;
                    button;
                };

                ~subtractiveWindow.view.keyDownAction_({
                    |view, char, modifiers, unicode, keycode|
                    ((unicode == 32) or: { keycode == 32 }).if({
                        ~toggleSubtractivePerformanceGate.();
                    });
                });

                ~subtractiveWindow.layout = VLayout(
                    StaticText().string_("Subtractive synthesis: source -> RLPF -> amp -> gate"),
                    StaticText().string_("Performance / Response"),
                    ~makeSubtractiveGateButton.(),
                    ~makeSubtractiveSlider.("crescendoTime", \crescendoTime, 0.0, 8.0, 0.001),
                    ~makeSubtractiveSlider.("decrescendoTime", \decrescendoTime, 0.0, 8.0, 0.001),
                    ~makeSubtractiveSlider.("freqLag", \freqLag, 0.0, 0.5, 0.001),
                    ~makeSubtractiveSlider.("ampAttack", \ampAttack, 0.001, 1.0, 0.001),
                    ~makeSubtractiveSlider.("ampRelease", \ampRelease, 0.001, 1.5, 0.001),
                    StaticText().string_("Articulation"),
                    ~makeSubtractiveToggle.("articulationOn", \articulationOn),
                    ~makeSubtractiveSlider.("articulationAttack", \articulationAttack, 0.001, 2.0, 0.001),
                    ~makeSubtractiveSlider.("articulationRelease", \articulationRelease, 0.001, 4.0, 0.001),
                    ~makeSubtractiveSlider.("outputLevel", \outputLevel, 0.0, 0.8, 0.001),
                    ~makeSubtractiveSlider.("ampMin", \ampMin, 0.0, 0.2, 0.001),
                    ~makeSubtractiveSlider.("ampMax", \ampMax, 0.01, 0.4, 0.001),
                    StaticText().string_("Oscillators"),
                    ~makeSubtractiveWaveMenu.("osc1Wave", \osc1Wave),
                    ~makeSubtractiveToggle.("osc2On", \osc2On),
                    ~makeSubtractiveWaveMenu.("osc2Wave", \osc2Wave),
                    ~makeSubtractiveSlider.("osc2Octave", \osc2Octave, -2.0, 2.0, 1.0),
                    ~makeSubtractiveSlider.("osc2DetuneCents", \osc2DetuneCents, -50.0, 50.0, 1.0),
                    ~makeSubtractiveSlider.("oscMix", \oscMix, 0.0, 1.0, 0.001),
                    ~makeSubtractiveSlider.("pulseWidth", \pulseWidth, 0.05, 0.95, 0.001),
                    ~makeSubtractiveSlider.("subMix", \subMix, 0.0, 1.0, 0.001),
                    ~makeSubtractiveSlider.("noiseMix", \noiseMix, 0.0, 0.5, 0.001),
                    StaticText().string_("Filter"),
                    ~makeSubtractiveToggle.("filterOn", \filterOn),
                    ~makeSubtractiveSlider.("Manual cutoff", \filterCutoff, 40.0, 16000.0, 1.0, \exp),
                    StaticText().string_("filterRq: low rq = sharper / more resonant"),
                    ~makeSubtractiveSlider.("filterRq", \filterRq, 0.05, 1.0, 0.001),
                    ~makeSubtractiveSlider.("filterMix", \filterMix, 0.0, 1.0, 0.001),
                    ~makeSubtractiveSlider.("filterLag", \filterLag, 0.0, 0.5, 0.001),
                    ~makeSubtractiveSlider.("keyTracking", \keyTracking, 0.0, 1.0, 0.001),
                    StaticText().string_("Filter Envelope"),
                    ~makeSubtractiveToggle.("filterEnvOn", \filterEnvOn),
                    ~makeSubtractiveSlider.("filterEnvAttack", \filterEnvAttack, 0.001, 2.0, 0.001),
                    ~makeSubtractiveSlider.("filterEnvDecay", \filterEnvDecay, 0.001, 4.0, 0.001),
                    ~makeSubtractiveSlider.("filterEnvSustain", \filterEnvSustain, 0.0, 1.0, 0.001),
                    ~makeSubtractiveSlider.("filterEnvRelease", \filterEnvRelease, 0.001, 6.0, 0.001),
                    ~makeSubtractiveSlider.("filterEnvAmountOctaves", \filterEnvAmountOctaves, 0.0, 5.0, 0.001),
                    StaticText().string_("Hand Tone Control (left-hand X -> cutoff)"),
                    ~makeSubtractiveToggle.("handToneOn", \handToneOn),
                    ~makeSubtractiveToneRangeSlider.("Hand tone range min", \toneMinCutoff),
                    ~makeSubtractiveToneRangeSlider.("Hand tone range max", \toneMaxCutoff),
                    ~makeSubtractiveToneInvertToggle.(),
                    StaticText().string_("Utility"),
                    Button()
                        .states_([["Reset defaults", Color.black, Color.gray(0.85)]])
                        .action_({ ~resetSubtractiveParams.(); })
                );
                ~subtractiveWindow.front;

                ~subtractiveMonitorWindow = Window(
                    "Subtractive Probe Monitor",
                    Rect(620, 80, 620, 420)
                );
                ~subtractiveMonitorLabels = ();

                ~makeSubtractiveMonitorLabel = { |key|
                    var label;
                    label = StaticText().string_("");
                    ~subtractiveMonitorLabels[key] = label;
                    label;
                };

                ~subtractiveMonitorWindow.layout = VLayout(
                    StaticText().string_("Subtractive probe monitor"),
                    HLayout(
                        Button()
                            .states_([["Open Scope", Color.black, Color.gray(0.85)]])
                            .action_({ ~openSubtractiveScope.(); }),
                        Button()
                            .states_([["Open FreqScope", Color.black, Color.gray(0.85)]])
                            .action_({ ~openSubtractiveFreqScope.(); })
                    ),
                    ~makeSubtractiveMonitorLabel.(\freq),
                    ~makeSubtractiveMonitorLabel.(\amp),
                    ~makeSubtractiveMonitorLabel.(\gate),
                    ~makeSubtractiveMonitorLabel.(\articulation),
                    ~makeSubtractiveMonitorLabel.(\filter),
                    ~makeSubtractiveMonitorLabel.(\filterEnv),
                    ~makeSubtractiveMonitorLabel.(\handTone),
                    ~makeSubtractiveMonitorLabel.(\oscillators),
                    ~makeSubtractiveMonitorLabel.(\output)
                );
                ~refreshSubtractiveMonitor.();
                ~subtractiveMonitorWindow.front;
            });
        }.defer; });

        OSCdef(\subtractiveProbeMonitor, { |msg, time, addr, recvPort|
            var nodeID;
            ~subtractiveDebugEvents.if({
                msg.postln;
            });
            // SendReply: [address, nodeID, replyID, targetFreq, targetAmp,
            // followedFreq, followedAmp, performanceEnv, articulationOn,
            // articulationGate, articulationEnv, filterEnvOn, filterEnvValue,
            // filterEnvAmountOctaves, filterEnvMultiplier, manualFilterCutoff,
            // mappedHandToneCutoff, effectiveCutoff].
            (msg.size >= 18).if({
                nodeID = msg[1].asInteger;
                ((~subtractiveSynth.isNil) or: {
                    nodeID == ~subtractiveSynth.nodeID
                }).if({
                    ~subtractiveMonitor[\targetFreq] = msg[3].asFloat;
                    ~subtractiveMonitor[\targetAmp] = msg[4].asFloat;
                    ~subtractiveMonitor[\followedFreq] = msg[5].asFloat;
                    ~subtractiveMonitor[\followedAmp] = msg[6].asFloat;
                    ~subtractiveMonitor[\performanceEnv] = msg[7].asFloat;
                    ~subtractiveParams[\articulationOn] = msg[8].asFloat;
                    ~subtractiveParams[\articulationGate] = msg[9].asFloat;
                    ~subtractiveMonitor[\articulationEnv] = msg[10].asFloat;
                    ~subtractiveParams[\filterEnvOn] = msg[11].asFloat;
                    ~subtractiveMonitor[\filterEnvValue] = msg[12].asFloat;
                    ~subtractiveParams[\filterEnvAmountOctaves] = msg[13].asFloat;
                    ~subtractiveMonitor[\filterEnvMultiplier] = msg[14].asFloat;
                    ~subtractiveMonitor[\manualFilterCutoff] = msg[15].asFloat;
                    ~subtractiveMonitor[\mappedHandToneCutoff] = msg[16].asFloat;
                    ~subtractiveMonitor[\effectiveCutoff] = msg[17].asFloat;
                    ~regularMonitorNotify.notNil.if({ ~regularMonitorNotify.(\subtractive, ~subtractiveMonitor); });
                    ~updateSubtractiveMonitor.();
                });
            });
        }, "/subtractiveProbe/monitor");

        // Python remains the source of truth for musical pitch.  This probe
        // follows final_freq only; it does not calculate scale or quantization.
        OSCdef(\subtractiveProbeFinalFreq, { |msg, time, addr, recvPort|
            var freq;
            freq = msg[1].asFloat.max(0);
            ~subtractiveMonitor[\targetFreq] = freq;
            ~subtractiveSynth.notNil.if({
                ~subtractiveSynth.set(\freq, freq);
            });
            ~updateSubtractiveMonitor.();
            ~subtractiveDebugEvents.if({
                ["subtractive final freq", freq].postln;
            });
        }, "/sample/right/pitch/final_freq");

        // /sample/left/pinch is mapped locally to the user-visible amp range.
        OSCdef(\subtractiveProbeLeftPinch, { |msg, time, addr, recvPort|
            var value, amp, ampMin, ampMax;
            ~subtractiveLastPinchAt = Main.elapsedTime;
            value = msg[1].asFloat.clip(0, 1);
            ampMin = ~subtractiveParams[\ampMin].min(~subtractiveParams[\ampMax]);
            ampMax = ~subtractiveParams[\ampMin].max(~subtractiveParams[\ampMax]);
            amp = value.linlin(0, 1, ampMin, ampMax);
            ~subtractiveMonitor[\targetAmp] = amp;
            ~subtractiveSynth.notNil.if({
                ~subtractiveSynth.set(\amp, amp);
            });
            ~updateSubtractiveMonitor.();
            ~subtractiveDebugEvents.if({
                ["subtractive amp", value, amp].postln;
            });
        }, "/sample/left/pinch");

        // V2a sample mapping only: Python derives this gate from left pinch
        // threshold + hysteresis; SC uses it for envelopes, not raw detection.
        OSCdef(\subtractiveProbeArticulationGate, { |msg, time, addr, recvPort|
            var gate;
            gate = msg[1].asFloat.clip(0, 1).round(1);
            ~setSubtractiveParam.(\articulationGate, gate);
            ~subtractiveDebugEvents.if({
                ["subtractive articulation gate", gate].postln;
            });
        }, "/sample/left/articulation/gate");

        // Left-hand index X remains a 0..1 tone candidate in Python. This
        // probe owns inversion, exponential cutoff mapping, and filter lag.
        OSCdef(\subtractiveProbeToneNorm, { |msg, time, addr, recvPort|
            var toneNorm;
            toneNorm = msg[1].asFloat.clip(0, 1);
            ~updateSubtractiveHandToneCutoff.(toneNorm);
            ~subtractiveDebugEvents.if({
                ["subtractive tone norm", toneNorm, ~subtractiveParams[\handToneCutoff]].postln;
            });
        }, "/sample/left/tone/norm");

        // Arm only after the first left-hand packet. Release amp directly so
        // ampMin and articulation bypass cannot leave a sustained tone.
        ~subtractiveLastPinchAt = nil;
        ~releaseSubtractiveInput = {
            ~subtractiveLastPinchAt = nil;
            ~subtractiveMonitor[\targetAmp] = 0;
            ~setSubtractiveParam.(\articulationGate, 0);
            ~subtractiveSynth.notNil.if({
                ~subtractiveSynth.set(\amp, 0);
            });
            ~updateSubtractiveMonitor.();
        };
        OSCdef(\subtractiveProbePanic, {
            ~releaseSubtractiveInput.();
        }, "/sample/panic");
        ~subtractiveInputWatchdog = Routine({
            loop {
                (~subtractiveLastPinchAt.notNil).if({
                    ((Main.elapsedTime - ~subtractiveLastPinchAt) >= 1.0).if({
                        ~releaseSubtractiveInput.();
                    });
                });
                0.1.wait;
            };
        }).play(SystemClock);

        // Shared, intentionally small probe-switch protocol.  It closes both
        // windows, frees this Synth, and unregisters only this probe's OSCdefs.
        ~activeProbeCleanup = {
            var windows, oscdefKeys;
            ~subtractiveInputWatchdog.notNil.if({ ~subtractiveInputWatchdog.stop; });
            ~subtractiveInputWatchdog = nil;
            ~subtractiveProbeInstance = (~subtractiveProbeInstance ? 0) + 1;
            ~subtractiveSynth.notNil.if({
                ~subtractiveSynth.free;
            });
            ~subtractiveSynth = nil;

            oscdefKeys = [
                \subtractiveProbeMonitor,
                \subtractiveProbeFinalFreq,
                \subtractiveProbeLeftPinch,
                \subtractiveProbeArticulationGate,
                \subtractiveProbePanic,
                \subtractiveProbeToneNorm
            ];
            oscdefKeys.do({ |key|
                try {
                    OSCdef(key).free;
                } { |error| };
            });

            windows = [~subtractiveWindow, ~subtractiveMonitorWindow];
            windows.do({ |window|
                window.notNil.if({
                    try {
                        window.close;
                    } { |error| };
                });
            });
            ~subtractiveWindow = nil;
            ~subtractiveMonitorWindow = nil;
            ~subtractiveFreqScope.notNil.if({
                try {
                    ~subtractiveFreqScope.kill;
                } { |error| };
            });
            ~subtractiveFreqScope = nil;
            ~subtractiveControls = nil;
            ~subtractiveMonitorLabels = nil;
            (~activeProbeName == \subtractiveProbe).if({
                ~activeProbeName = nil;
            });
        };
        ~activeProbeName = \subtractiveProbe;

        "Listening for sample mapping events with the subtractive probe.".postln;
        "Subtractive Probe Controls and Monitor windows are available.".postln;
        "Use the Gate button or spacebar in the control window to perform.".postln;
    });
});
)

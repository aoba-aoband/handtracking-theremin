/*
Basic SuperCollider OSC receiver for platform control events.

This file should receive generic control events from the Python platform.
The neutral /hand/... events can be posted for inspection only.
The /sample/... mappings are example musical mappings layered on top of the
neutral /hand/... control events. They are not fixed platform rules.

Coordinate notes:
- /hand/0 is the first hand reported by MediaPipe, not a fixed right or left hand.
- Image y is normalized top-to-bottom: top is 0, bottom is 1.
*/

(
var basicProbeInstance;

// A probe owns the sample-mapping OSC handlers while it is active.  Keep this
// small shared cleanup hook so evaluating another probe does not double-play.
~activeProbeCleanup.notNil.if({
    ~activeProbeCleanup.();
});
~activeProbeCleanup = nil;
// Also invalidate a subtractive evaluation that may still be waiting for the
// server to boot before it creates its Synth or windows.
~subtractiveProbeInstance = (~subtractiveProbeInstance ? 0) + 1;
basicProbeInstance = (~basicProbeInstance ? 0) + 1;
~basicProbeInstance = basicProbeInstance;

s.waitForBoot({
    (~basicProbeInstance == basicProbeInstance).if({
    ~debugHandEvents = false;
    ~debugSampleEvents = false;
    ~debugProbeMonitor = false;

    ~probeDefaults = (
        freqLag: 0.08,
        ampLag: 0.08,
        portamentoOn: 0,
        portamentoTime: 0.15,
        softClipOn: 0,
        softClipDrive: 2.0,
        softClipMix: 1.0,
        additiveOn: 0,
        additiveMix: 0.0,
        additiveGain: 1.0,
        harmonic1: 1.0,
        harmonic2: 0.0,
        harmonic3: 0.0,
        harmonic4: 0.0,
        harmonic5: 0.0,
        harmonic6: 0.0,
        harmonic7: 0.0,
        harmonic8: 0.0,
        harmonic9: 0.0,
        harmonic10: 0.0,
        harmonic11: 0.0,
        harmonic12: 0.0,
        filterOn: 0,
        filterCutoff: 5000,
        filterRq: 0.7,
        filterMix: 1.0,
        filterLag: 0.05,
        delayOn: 0,
        delayMix: 0.0,
        delayTime: 0.25,
        delayFeedback: 0.25,
        delayFilterCutoff: 4000,
        delayFilterRq: 0.5,
        delayLag: 0.05,
        reverbOn: 0,
        reverbMix: 0.0,
        reverbRoom: 0.4,
        reverbDamp: 0.5,
        outputLevel: 0.7,
        performanceGate: 0,
        crescendoTime: 1.5,
        decrescendoTime: 1.5,
        monitorOn: 1,
        monitorRate: 10,
        ampMin: 0.02,
        ampMax: 0.25
    );
    ~probeParams = ~probeDefaults.copy;
    ~probeSynthParamKeys = [
        \freqLag,
        \ampLag,
        \portamentoOn,
        \portamentoTime,
        \softClipOn,
        \softClipDrive,
        \softClipMix,
        \additiveOn,
        \additiveMix,
        \additiveGain,
        \harmonic1,
        \harmonic2,
        \harmonic3,
        \harmonic4,
        \harmonic5,
        \harmonic6,
        \harmonic7,
        \harmonic8,
        \harmonic9,
        \harmonic10,
        \harmonic11,
        \harmonic12,
        \filterOn,
        \filterCutoff,
        \filterRq,
        \filterMix,
        \filterLag,
        \delayOn,
        \delayMix,
        \delayTime,
        \delayFeedback,
        \delayFilterCutoff,
        \delayFilterRq,
        \delayLag,
        \reverbOn,
        \reverbMix,
        \reverbRoom,
        \reverbDamp,
        \outputLevel,
        \performanceGate,
        \crescendoTime,
        \decrescendoTime,
        \monitorOn,
        \monitorRate
    ];

    ~probeMonitor = (
        targetFreq: 440.0,
        targetAmp: 0.05,
        followedFreq: 440.0,
        followedAmp: 0.05,
        performanceEnv: 0.0,
        filterFreq: 5000.0
    );
    ~probeHistoryMax = 50;
    ~probeHistory = [[440.0, 440.0]];
    ~probeHarmonicKeys = [
        \harmonic1,
        \harmonic2,
        \harmonic3,
        \harmonic4,
        \harmonic5,
        \harmonic6,
        \harmonic7,
        \harmonic8,
        \harmonic9,
        \harmonic10,
        \harmonic11,
        \harmonic12
    ];

    SynthDef(\basicOscProbe, { |out = 0, freq = 440, amp = 0.05, uiMute = 0,
        freqLag = 0.08, ampLag = 0.08,
        portamentoOn = 0, portamentoTime = 0.15,
        softClipOn = 0, softClipDrive = 2.0, softClipMix = 1.0,
        additiveOn = 0, additiveMix = 0.0, additiveGain = 1.0,
        harmonic1 = 1.0, harmonic2 = 0.0, harmonic3 = 0.0,
        harmonic4 = 0.0, harmonic5 = 0.0, harmonic6 = 0.0,
        harmonic7 = 0.0, harmonic8 = 0.0, harmonic9 = 0.0,
        harmonic10 = 0.0, harmonic11 = 0.0, harmonic12 = 0.0,
        filterOn = 0, filterCutoff = 5000, filterRq = 0.7,
        filterMix = 1.0, filterLag = 0.05,
        delayOn = 0, delayMix = 0.0, delayTime = 0.25,
        delayFeedback = 0.25, delayFilterCutoff = 4000,
        delayFilterRq = 0.5, delayLag = 0.05,
        reverbOn = 0, reverbMix = 0.0, reverbRoom = 0.4,
        reverbDamp = 0.5,
        outputLevel = 0.7,
        performanceGate = 0, crescendoTime = 1.5, decrescendoTime = 1.5,
        monitorOn = 1, monitorRate = 10|

        var freqFollowTime, followedFreq, followedAmp;
        var performanceEnv, base, additive, harmonicWeight, oscMix, source;
        var dry, clipped, shaped;
        var filterFreq, filtered, filteredMix;
        var fxIn, delayFilterFreq, feedback, delayBlend;
        var fb, delayInput, delayTap, delayFiltered, afterDelay;
        var reverbWet, reverbBlend, afterReverb, sig, monitorTrig;

        freqFollowTime = Select.kr(
            portamentoOn.clip(0, 1),
            [freqLag.max(0), portamentoTime.max(0)]
        );
        followedFreq = Lag.kr(freq.max(20), freqFollowTime);
        followedAmp = Lag.kr(amp.max(0), ampLag.max(0));
        performanceEnv = LagUD.kr(
            performanceGate.clip(0, 1),
            crescendoTime.max(0),
            decrescendoTime.max(0)
        );

        base = SinOsc.ar(followedFreq);
        harmonicWeight = (
            harmonic1 + harmonic2 + harmonic3 + harmonic4
            + harmonic5 + harmonic6 + harmonic7 + harmonic8
            + harmonic9 + harmonic10 + harmonic11 + harmonic12
        ).max(0.001);
        additive = (
            (SinOsc.ar(followedFreq * 1) * harmonic1)
            + (SinOsc.ar(followedFreq * 2) * harmonic2)
            + (SinOsc.ar(followedFreq * 3) * harmonic3)
            + (SinOsc.ar(followedFreq * 4) * harmonic4)
            + (SinOsc.ar(followedFreq * 5) * harmonic5)
            + (SinOsc.ar(followedFreq * 6) * harmonic6)
            + (SinOsc.ar(followedFreq * 7) * harmonic7)
            + (SinOsc.ar(followedFreq * 8) * harmonic8)
            + (SinOsc.ar(followedFreq * 9) * harmonic9)
            + (SinOsc.ar(followedFreq * 10) * harmonic10)
            + (SinOsc.ar(followedFreq * 11) * harmonic11)
            + (SinOsc.ar(followedFreq * 12) * harmonic12)
        ) / harmonicWeight;
        additive = additive * additiveGain.clip(0, 2);
        oscMix = additiveOn.clip(0, 1) * additiveMix.clip(0, 1);
        source = SelectX.ar(oscMix, [base, additive]);

        dry = source * followedAmp;
        clipped = (dry * softClipDrive.max(1)).tanh;
        shaped = SelectX.ar(
            softClipOn.clip(0, 1) * softClipMix.clip(0, 1),
            [dry, clipped]
        );
        filterFreq = Lag.kr(filterCutoff.clip(40, 18000), filterLag.max(0));
        filtered = RLPF.ar(shaped, filterFreq, filterRq.clip(0.05, 1.0));
        filteredMix = SelectX.ar(
            filterOn.clip(0, 1) * filterMix.clip(0, 1),
            [shaped, filtered]
        );
        fxIn = filteredMix ! 2;

        delayFilterFreq = Lag.kr(delayFilterCutoff.clip(100, 12000), delayLag.max(0));
        feedback = delayFeedback.clip(0, 0.85);
        delayBlend = delayOn.clip(0, 1) * delayMix.clip(0, 1);
        fb = LocalIn.ar(2);
        delayInput = fxIn + (fb * feedback);
        delayTap = DelayC.ar(delayInput, 2.0, delayTime.clip(0.02, 2.0));
        delayFiltered = RLPF.ar(delayTap, delayFilterFreq, delayFilterRq.clip(0.05, 1.0));
        LocalOut.ar(delayFiltered * delayOn.clip(0, 1));
        afterDelay = (fxIn * (1 - delayBlend)) + (delayFiltered * delayBlend);

        reverbBlend = reverbOn.clip(0, 1) * reverbMix.clip(0, 1);
        reverbWet = FreeVerb2.ar(
            afterDelay[0],
            afterDelay[1],
            1.0,
            reverbRoom.clip(0, 1),
            reverbDamp.clip(0, 1)
        );
        afterReverb = (afterDelay * (1 - reverbBlend)) + (reverbWet * reverbBlend);

        sig = afterReverb * outputLevel.clip(0, 1) * performanceEnv;
        monitorTrig = Impulse.kr(monitorRate.clip(0.1, 30)) * monitorOn.clip(0, 1);
        SendReply.kr(
            monitorTrig,
            '/basicOscProbe/monitor',
            [followedFreq, followedAmp, performanceEnv, filterFreq]
        );
        Out.ar(out, sig * (1 - uiMute.clip(0, 1)));
    }).add;

    s.sync;

    ~basicReceiverSynth.notNil.if({
        ~basicReceiverSynth.free;
    });
    "creating probe synth".postln;
    ~basicReceiverSynth = Synth(\basicOscProbe, [
        \freqLag, ~probeParams[\freqLag],
        \ampLag, ~probeParams[\ampLag],
        \portamentoOn, ~probeParams[\portamentoOn],
        \portamentoTime, ~probeParams[\portamentoTime],
        \softClipOn, ~probeParams[\softClipOn],
        \softClipDrive, ~probeParams[\softClipDrive],
        \softClipMix, ~probeParams[\softClipMix],
        \additiveOn, ~probeParams[\additiveOn],
        \additiveMix, ~probeParams[\additiveMix],
        \additiveGain, ~probeParams[\additiveGain],
        \harmonic1, ~probeParams[\harmonic1],
        \harmonic2, ~probeParams[\harmonic2],
        \harmonic3, ~probeParams[\harmonic3],
        \harmonic4, ~probeParams[\harmonic4],
        \harmonic5, ~probeParams[\harmonic5],
        \harmonic6, ~probeParams[\harmonic6],
        \harmonic7, ~probeParams[\harmonic7],
        \harmonic8, ~probeParams[\harmonic8],
        \harmonic9, ~probeParams[\harmonic9],
        \harmonic10, ~probeParams[\harmonic10],
        \harmonic11, ~probeParams[\harmonic11],
        \harmonic12, ~probeParams[\harmonic12],
        \filterOn, ~probeParams[\filterOn],
        \filterCutoff, ~probeParams[\filterCutoff],
        \filterRq, ~probeParams[\filterRq],
        \filterMix, ~probeParams[\filterMix],
        \filterLag, ~probeParams[\filterLag],
        \delayOn, ~probeParams[\delayOn],
        \delayMix, ~probeParams[\delayMix],
        \delayTime, ~probeParams[\delayTime],
        \delayFeedback, ~probeParams[\delayFeedback],
        \delayFilterCutoff, ~probeParams[\delayFilterCutoff],
        \delayFilterRq, ~probeParams[\delayFilterRq],
        \delayLag, ~probeParams[\delayLag],
        \reverbOn, ~probeParams[\reverbOn],
        \reverbMix, ~probeParams[\reverbMix],
        \reverbRoom, ~probeParams[\reverbRoom],
        \reverbDamp, ~probeParams[\reverbDamp],
        \outputLevel, ~probeParams[\outputLevel],
        \performanceGate, ~probeParams[\performanceGate],
        \crescendoTime, ~probeParams[\crescendoTime],
        \decrescendoTime, ~probeParams[\decrescendoTime],
        \monitorOn, ~probeParams[\monitorOn],
        \monitorRate, ~probeParams[\monitorRate]
    ]);

    ~fmtProbeNumber = { |value, step = 0.001|
        (value ? 0).asFloat.round(step).asString;
    };

    ~fmtProbeHz = { |value|
        ~fmtProbeNumber.(value, 0.1) ++ " Hz";
    };

    ~fmtProbeFreqTick = { |value|
        var freq;
        freq = value.asFloat;
        (freq >= 1000).if({
            ~fmtProbeNumber.(freq / 1000, 0.1) ++ "k";
        }, {
            freq.asInteger.asString;
        });
    };

    ~fmtProbeOnOff = { |value|
        ((value ? 0).asFloat >= 0.5).if({ "ON" }, { "OFF" });
    };

    ~refreshProbeMonitor = {
        var labels;
        labels = ~probeMonitorLabels;
        labels.notNil.if({
            labels[\freq].notNil.if({
                labels[\freq].string_(
                    "targetFreq: " ++ ~fmtProbeHz.(~probeMonitor[\targetFreq])
                    ++ "    followedFreq: " ++ ~fmtProbeHz.(~probeMonitor[\followedFreq])
                );
            });
            labels[\amp].notNil.if({
                labels[\amp].string_(
                    "targetAmp: " ++ ~fmtProbeNumber.(~probeMonitor[\targetAmp], 0.001)
                    ++ "    followedAmp: " ++ ~fmtProbeNumber.(~probeMonitor[\followedAmp], 0.001)
                );
            });
            labels[\gate].notNil.if({
                labels[\gate].string_(
                    "Gate: " ++ ~fmtProbeOnOff.(~probeParams[\performanceGate])
                    ++ "    env " ++ ~fmtProbeNumber.(~probeMonitor[\performanceEnv], 0.01)
                );
            });
            labels[\level].notNil.if({
                labels[\level].string_(
                    "outputLevel: " ++ ~fmtProbeNumber.(~probeParams[\outputLevel], 0.001)
                    ++ "    ampRange: "
                    ++ ~fmtProbeNumber.(~probeParams[\ampMin], 0.001)
                    ++ " - " ++ ~fmtProbeNumber.(~probeParams[\ampMax], 0.001)
                );
            });
            labels[\softClip].notNil.if({
                labels[\softClip].string_(
                    "SoftClip: " ++ ~fmtProbeOnOff.(~probeParams[\softClipOn])
                    ++ "    drive " ++ ~fmtProbeNumber.(~probeParams[\softClipDrive], 0.01)
                    ++ "    mix " ++ ~fmtProbeNumber.(~probeParams[\softClipMix], 0.001)
                );
            });
            labels[\filter].notNil.if({
                labels[\filter].string_(
                    "Filter: " ++ ~fmtProbeOnOff.(~probeParams[\filterOn])
                    ++ "    cutoff " ++ ~fmtProbeHz.(~probeParams[\filterCutoff])
                    ++ "    rq " ++ ~fmtProbeNumber.(~probeParams[\filterRq], 0.01)
                    ++ "    mix " ++ ~fmtProbeNumber.(~probeParams[\filterMix], 0.001)
                );
            });
            labels[\filterFreq].notNil.if({
                labels[\filterFreq].string_(
                    "filterFreq: " ++ ~fmtProbeHz.(~probeMonitor[\filterFreq])
                    ++ "    filterLag " ++ ~fmtProbeNumber.(~probeParams[\filterLag], 0.001)
                );
            });
            labels[\additive].notNil.if({
                labels[\additive].string_(
                    "Additive: " ++ ~fmtProbeOnOff.(~probeParams[\additiveOn])
                    ++ "    mix " ++ ~fmtProbeNumber.(~probeParams[\additiveMix], 0.001)
                    ++ "    gain " ++ ~fmtProbeNumber.(~probeParams[\additiveGain], 0.01)
                );
            });
            labels[\delay].notNil.if({
                labels[\delay].string_(
                    "Delay: " ++ ~fmtProbeOnOff.(~probeParams[\delayOn])
                    ++ "    time " ++ ~fmtProbeNumber.(~probeParams[\delayTime], 0.001)
                    ++ "    feedback " ++ ~fmtProbeNumber.(~probeParams[\delayFeedback], 0.001)
                    ++ "    mix " ++ ~fmtProbeNumber.(~probeParams[\delayMix], 0.001)
                    ++ "    filter " ++ ~fmtProbeHz.(~probeParams[\delayFilterCutoff])
                );
            });
            labels[\reverb].notNil.if({
                labels[\reverb].string_(
                    "Reverb: " ++ ~fmtProbeOnOff.(~probeParams[\reverbOn])
                    ++ "    mix " ++ ~fmtProbeNumber.(~probeParams[\reverbMix], 0.001)
                    ++ "    room " ++ ~fmtProbeNumber.(~probeParams[\reverbRoom], 0.01)
                    ++ "    damp " ++ ~fmtProbeNumber.(~probeParams[\reverbDamp], 0.01)
                );
            });
        });
    };

    ~addProbeHistoryPoint = {
        ~probeHistory = ~probeHistory.add([
            (~probeMonitor[\targetFreq] ? 440).asFloat,
            (~probeMonitor[\followedFreq] ? 440).asFloat
        ]);
        (~probeHistory.size > ~probeHistoryMax).if({
            ~probeHistory = ~probeHistory.copyRange(
                ~probeHistory.size - ~probeHistoryMax,
                ~probeHistory.size - 1
            );
        });
    };

    ~drawProbeLine = { |startPoint, endPoint, color, width = 1|
        Pen.width = width;
        color.set;
        Pen.moveTo(startPoint);
        Pen.lineTo(endPoint);
        Pen.stroke;
    };

    ~drawProbeText = { |string, point, color|
        string.asString.drawAtPoint(point, Font.default, color ? Color.gray(0.35));
    };

    ~drawProbePoints = { |points, color, width = 2|
        (points.size > 1).if({
            Pen.width = width;
            color.set;
            points.do({ |point, index|
                (index == 0).if({
                    Pen.moveTo(point);
                }, {
                    Pen.lineTo(point);
                });
            });
            Pen.stroke;
        });
    };

    ~probePanelRect = { |view|
        var bounds, rect;
        bounds = view.bounds;
        Color.gray(0.96).set;
        Pen.fillRect(bounds);
        rect = Rect(38, 14, bounds.width - 56, bounds.height - 34);
        Color.gray(0.72).set;
        Pen.width = 1;
        Pen.strokeRect(rect);
        rect;
    };

    ~probeLogFreqX = { |freq, rect|
        var minFreq, maxFreq, minLog, maxLog, valueLog, norm;
        minFreq = 80.0;
        maxFreq = 12000.0;
        minLog = minFreq.log;
        maxLog = maxFreq.log;
        valueLog = freq.clip(minFreq, maxFreq).log;
        norm = ((valueLog - minLog) / (maxLog - minLog)).clip(0, 1);
        rect.left + (norm * rect.width);
    };

    ~drawFilterVisual = { |view|
        var plot, cutoff, rq, mix, on, activeMix, cutoffX, points;
        var steps, minFreq, maxFreq, minLog, maxLog, freqRatio, responseDenom;
        var freq, norm, x, y, response, visualResponse, db, clippedDb, dbNorm;
        var minDb, maxDb, dbTicks, tickDb, tickY, tickFreqs, tickX, tickLabel;
        var peakDb, peakClipped;
        plot = ~probePanelRect.(view);
        cutoff = (~probeParams[\filterCutoff] ? 5000).asFloat.clip(80, 12000);
        rq = (~probeParams[\filterRq] ? 0.7).asFloat.clip(0.05, 1.0);
        mix = (~probeParams[\filterMix] ? 1.0).asFloat.clip(0, 1);
        on = (~probeParams[\filterOn] ? 0).asFloat.clip(0, 1);
        activeMix = on * mix;
        cutoffX = ~probeLogFreqX.(cutoff, plot);
        minDb = -36.0;
        maxDb = 12.0;
        peakDb = minDb;
        peakClipped = false;

        dbTicks = [
            [12, "+12 dB"],
            [6, "+6 dB"],
            [0, "0 dB"],
            [-12, "-12 dB"],
            [-24, "-24 dB"],
            [-36, "-36 dB"]
        ];
        dbTicks.do({ |tickSpec|
            tickDb = tickSpec[0];
            tickY = plot.bottom - ((((tickDb - minDb) / (maxDb - minDb)).clip(0, 1)) * plot.height);
            ~drawProbeLine.(
                Point(plot.left, tickY),
                Point(plot.right, tickY),
                (tickDb == 0).if({ Color.gray(0.58) }, { Color.gray(0.88) }),
                (tickDb == 0).if({ 1.5 }, { 1 })
            );
            ~drawProbeText.(
                tickSpec[1],
                Point(2, tickY - 7),
                (tickDb == 0).if({ Color.gray(0.25) }, { Color.gray(0.45) })
            );
        });

        tickFreqs = [80, 100, 200, 500, 1000, 2000, 5000, 10000, 12000];
        tickFreqs.do({ |tickFreq|
            tickX = ~probeLogFreqX.(tickFreq, plot);
            ~drawProbeLine.(Point(tickX, plot.top), Point(tickX, plot.bottom), Color.gray(0.88), 1);
            tickLabel = ~fmtProbeFreqTick.(tickFreq);
            ~drawProbeText.(tickLabel, Point(tickX - 10, plot.bottom + 4), Color.gray(0.35));
        });

        Color(0.55, 0.65, 0.95, activeMix * 0.25).set;
        Pen.fillRect(Rect(cutoffX, plot.top, plot.right - cutoffX, plot.height));
        ~drawProbeLine.(
            Point(plot.left, plot.top + (plot.height * 0.12)),
            Point(plot.right, plot.top + (plot.height * 0.12)),
            Color.gray(0.78),
            1
        );

        steps = 72;
        minFreq = 80.0;
        maxFreq = 12000.0;
        minLog = minFreq.log;
        maxLog = maxFreq.log;
        points = [];
        steps.do({ |index|
            norm = index / (steps - 1);
            freq = (minLog + (norm * (maxLog - minLog))).exp;
            x = plot.left + (norm * plot.width);
            freqRatio = freq / cutoff;
            responseDenom = (
                (1 - (freqRatio * freqRatio)).squared
                + (rq * freqRatio).squared
            ).sqrt.max(0.001);
            response = 1 / responseDenom;
            visualResponse = (1 - activeMix) + (response * activeMix);
            db = 20 * (visualResponse.max(0.0001).log / 10.log);
            peakDb = peakDb.max(db);
            peakClipped = peakClipped or: { db > maxDb };
            clippedDb = db.clip(minDb, maxDb);
            dbNorm = ((clippedDb - minDb) / (maxDb - minDb)).clip(0, 1);
            y = plot.bottom - (dbNorm * plot.height);
            points = points.add(Point(x, y));
        });

        ~drawProbePoints.(
            points,
            (on >= 0.5).if({ Color(0.05, 0.22, 0.65) }, { Color.gray(0.55) }),
            2
        );
        ~drawProbeLine.(Point(cutoffX, plot.top), Point(cutoffX, plot.bottom), Color(0.85, 0.18, 0.12), 2);
        ~drawProbeText.(
            "cutoff " ++ ~fmtProbeHz.(cutoff),
            Point((cutoffX + 4).min(plot.right - 92), plot.top + 4),
            Color(0.85, 0.18, 0.12)
        );
        ~drawProbeText.(
            "rq " ++ ~fmtProbeNumber.(rq, 0.01)
            ++ "   mix " ++ ~fmtProbeNumber.(mix, 0.01),
            Point(plot.left + 6, plot.top + 20),
            Color.gray(0.25)
        );
        ~drawProbeText.(
            "RLPF-like response, not measured",
            Point(plot.left + 6, plot.top + 36),
            Color.gray(0.35)
        );
        ~drawProbeText.(
            "dB scale   low rq = sharper / more resonant",
            Point(plot.left + 6, plot.top + 52),
            Color.gray(0.35)
        );
        peakClipped.if({
            ~drawProbeText.(
                "peak > +" ++ maxDb.asInteger.asString ++ " dB",
                Point(plot.right - 102, plot.top + 20),
                Color(0.85, 0.18, 0.12)
            );
        });
        ~drawProbeLine.(Point(plot.left, plot.bottom), Point(plot.right, plot.bottom), Color.gray(0.4), 1);
        ~drawProbeLine.(Point(plot.left, plot.top), Point(plot.left, plot.bottom), Color.gray(0.4), 1);
    };

    ~drawSoftClipVisual = { |view|
        var plot, drive, mix, on, activeMix, dryPoints, shapedPoints;
        var steps, input, clipped, output, norm, x, dryY, shapedY, centerY;
        plot = ~probePanelRect.(view);
        drive = (~probeParams[\softClipDrive] ? 2.0).asFloat.clip(1, 20);
        mix = (~probeParams[\softClipMix] ? 1.0).asFloat.clip(0, 1);
        on = (~probeParams[\softClipOn] ? 0).asFloat.clip(0, 1);
        activeMix = on * mix;
        steps = 90;
        dryPoints = [];
        shapedPoints = [];
        centerY = plot.top + (plot.height * 0.5);

        ~drawProbeLine.(Point(plot.left, centerY), Point(plot.right, centerY), Color.gray(0.82), 1);
        ~drawProbeLine.(
            Point(plot.left + (plot.width * 0.5), plot.top),
            Point(plot.left + (plot.width * 0.5), plot.bottom),
            Color.gray(0.82),
            1
        );

        steps.do({ |index|
            norm = index / (steps - 1);
            input = -1.0 + (norm * 2.0);
            clipped = (input * drive).tanh;
            output = (input * (1 - activeMix)) + (clipped * activeMix);
            x = plot.left + (norm * plot.width);
            dryY = centerY - ((input / 1.12) * (plot.height * 0.5));
            shapedY = centerY - ((output / 1.12) * (plot.height * 0.5));
            dryPoints = dryPoints.add(Point(x, dryY));
            shapedPoints = shapedPoints.add(Point(x, shapedY));
        });

        ~drawProbePoints.(dryPoints, Color.gray(0.68), 1);
        ~drawProbePoints.(
            shapedPoints,
            (on >= 0.5).if({ Color(0.0, 0.42, 0.72) }, { Color.gray(0.45) }),
            2
        );
    };

    ~drawPitchFollowVisual = { |view|
        var plot, hist, minFreq, maxFreq, range, pointCount, denom;
        var targetPoints, followedPoints, freqToY, x;
        plot = ~probePanelRect.(view);
        hist = ~probeHistory ? [[440.0, 440.0]];
        minFreq = 20000.0;
        maxFreq = 20.0;
        hist.do({ |point|
            minFreq = minFreq.min(point[0]).min(point[1]);
            maxFreq = maxFreq.max(point[0]).max(point[1]);
        });
        range = (maxFreq - minFreq).max(1);
        minFreq = (minFreq - (range * 0.12)).max(20);
        maxFreq = maxFreq + (range * 0.12);
        freqToY = { |freq|
            plot.bottom - (((freq - minFreq) / (maxFreq - minFreq)).clip(0, 1) * plot.height);
        };
        pointCount = hist.size;
        denom = (pointCount - 1).max(1);
        targetPoints = [];
        followedPoints = [];

        ~drawProbeLine.(Point(plot.left, plot.top), Point(plot.left, plot.bottom), Color.gray(0.4), 1);
        ~drawProbeLine.(Point(plot.left, plot.bottom), Point(plot.right, plot.bottom), Color.gray(0.4), 1);
        hist.do({ |point, index|
            x = plot.left + ((index / denom) * plot.width);
            targetPoints = targetPoints.add(Point(x, freqToY.(point[0])));
            followedPoints = followedPoints.add(Point(x, freqToY.(point[1])));
        });
        ~drawProbePoints.(targetPoints, Color(0.1, 0.22, 0.82), 1.5);
        ~drawProbePoints.(followedPoints, Color(0.85, 0.28, 0.08), 2.5);
    };

    ~drawHarmonicVisual = { |view|
        var plot, keys, on, active, laneWidth, barWidth, x, value, barHeight;
        plot = ~probePanelRect.(view);
        keys = ~probeHarmonicKeys;
        on = (~probeParams[\additiveOn] ? 0).asFloat.clip(0, 1);
        active = (on * (~probeParams[\additiveMix] ? 0).asFloat.clip(0, 1)).max(0.18);
        laneWidth = plot.width / keys.size;
        barWidth = laneWidth * 0.62;

        ~drawProbeLine.(Point(plot.left, plot.bottom), Point(plot.right, plot.bottom), Color.gray(0.4), 1);
        keys.do({ |key, index|
            value = (~probeParams[key] ? 0).asFloat.clip(0, 1);
            x = plot.left + (index * laneWidth) + ((laneWidth - barWidth) * 0.5);
            barHeight = value * plot.height;
            Color(0.1, 0.36, 0.68, active).set;
            Pen.fillRect(Rect(x, plot.bottom - barHeight, barWidth, barHeight));
            ~drawProbeText.("H" ++ (index + 1).asString, Point(x - 1, plot.bottom + 4), Color.gray(0.35));
        });
    };

    ~drawDelayVisual = { |view|
        var plot, on, mix, time, feedback, delayFilterCutoff;
        var spacing, repeats, x, height, alpha;
        plot = ~probePanelRect.(view);
        on = (~probeParams[\delayOn] ? 0).asFloat.clip(0, 1);
        mix = (~probeParams[\delayMix] ? 0).asFloat.clip(0, 1);
        time = (~probeParams[\delayTime] ? 0.25).asFloat.clip(0.02, 2.0);
        feedback = (~probeParams[\delayFeedback] ? 0.25).asFloat.clip(0, 0.85);
        delayFilterCutoff = (~probeParams[\delayFilterCutoff] ? 4000).asFloat.clip(100, 12000);
        spacing = time.linlin(0.02, 2.0, plot.width * 0.08, plot.width * 0.34);
        repeats = 8;

        ~drawProbeLine.(Point(plot.left, plot.bottom), Point(plot.right, plot.bottom), Color.gray(0.4), 1);
        ~drawProbeLine.(Point(plot.left, plot.top), Point(plot.left, plot.bottom), Color.gray(0.4), 1);
        repeats.do({ |index|
            x = plot.left + (index * spacing);
            (x <= plot.right).if({
                height = plot.height * (0.9 * (feedback.max(0.05) ** index)) * (0.35 + (mix * 0.65));
                alpha = (0.18 + (on * mix * (feedback.max(0.18) ** index))).clip(0.12, 0.9);
                Color(0.0, 0.42, 0.72, alpha).set;
                Pen.fillRect(Rect(x - 5, plot.bottom - height, 10, height));
            });
        });
        ~drawProbeText.("short", Point(plot.left, plot.bottom + 4), Color.gray(0.35));
        ~drawProbeText.("long", Point(plot.right - 28, plot.bottom + 4), Color.gray(0.35));
        ~drawProbeText.(
            "delay filter " ++ ~fmtProbeHz.(delayFilterCutoff),
            Point(plot.left + 6, plot.top + 4),
            Color(0.85, 0.18, 0.12)
        );
    };

    ~refreshProbeVisuals = {
        var labels, views;
        labels = ~probeVisualLabels;
        labels.notNil.if({
            labels[\filter].notNil.if({
                labels[\filter].string_(
                    "LPF / Filter    "
                    ++ ~fmtProbeOnOff.(~probeParams[\filterOn])
                    ++ "    cutoff " ++ ~fmtProbeHz.(~probeParams[\filterCutoff])
                    ++ "    rq " ++ ~fmtProbeNumber.(~probeParams[\filterRq], 0.01)
                    ++ "    mix " ++ ~fmtProbeNumber.(~probeParams[\filterMix], 0.001)
                    ++ "    lag " ++ ~fmtProbeNumber.(~probeParams[\filterLag], 0.001)
                );
            });
            labels[\softClip].notNil.if({
                labels[\softClip].string_(
                    "Soft Clip Curve    "
                    ++ ~fmtProbeOnOff.(~probeParams[\softClipOn])
                    ++ "    drive " ++ ~fmtProbeNumber.(~probeParams[\softClipDrive], 0.01)
                    ++ "    mix " ++ ~fmtProbeNumber.(~probeParams[\softClipMix], 0.001)
                );
            });
            labels[\pitch].notNil.if({
                labels[\pitch].string_(
                    "Pitch Follow / Portamento    target "
                    ++ ~fmtProbeHz.(~probeMonitor[\targetFreq])
                    ++ "    followed " ++ ~fmtProbeHz.(~probeMonitor[\followedFreq])
                    ++ "    mode " ++ ((~probeParams[\portamentoOn] ? 0).asInteger == 1).if({ "portamento" }, { "freqLag" })
                    ++ "    freqLag " ++ ~fmtProbeNumber.(~probeParams[\freqLag], 0.001)
                    ++ "    portamentoTime " ++ ~fmtProbeNumber.(~probeParams[\portamentoTime], 0.001)
                );
            });
            labels[\harmonics].notNil.if({
                labels[\harmonics].string_(
                    "Additive Harmonics    "
                    ++ ~fmtProbeOnOff.(~probeParams[\additiveOn])
                    ++ "    mix " ++ ~fmtProbeNumber.(~probeParams[\additiveMix], 0.001)
                    ++ "    gain " ++ ~fmtProbeNumber.(~probeParams[\additiveGain], 0.01)
                );
            });
            labels[\delay].notNil.if({
                labels[\delay].string_(
                    "Filtered Delay    "
                    ++ ~fmtProbeOnOff.(~probeParams[\delayOn])
                    ++ "    time " ++ ~fmtProbeNumber.(~probeParams[\delayTime], 0.001)
                    ++ "    feedback " ++ ~fmtProbeNumber.(~probeParams[\delayFeedback], 0.001)
                    ++ "    mix " ++ ~fmtProbeNumber.(~probeParams[\delayMix], 0.001)
                    ++ "    filter " ++ ~fmtProbeHz.(~probeParams[\delayFilterCutoff])
                );
            });
        });

        views = ~probeVisualViews;
        views.notNil.if({
            views.keysValuesDo({ |key, view|
                view.notNil.if({
                    view.refresh;
                });
            });
        });
    };

    ~updateProbeMonitor = {
        {
            ~refreshProbeMonitor.();
            ~refreshProbeVisuals.();
        }.defer;
    };

    ~setProbeParam = { |key, value|
        ~probeParams[key] = value;
        (~basicReceiverSynth.notNil and: {
            ~probeSynthParamKeys.includes(key)
        }).if({
            ~basicReceiverSynth.set(key, value);
        });
        ~updateProbeMonitor.();
    };

    ~resetProbeParams = {
        ~probeDefaults.keysValuesDo({ |key, value|
            ~setProbeParam.(key, value);
        });
    };

    ~setPerformanceGate = { |value|
        var gate;
        gate = value.clip(0, 1).asInteger;
        ~setProbeParam.(\performanceGate, gate);
        {
            ~probeControls.notNil.if({
                ~probeControls[\performanceGate].notNil.if({
                    ~probeControls[\performanceGate].value_(gate);
                });
            });
        }.defer;
    };

    ~togglePerformanceGate = {
        var current;
        current = (~probeParams[\performanceGate] ? 0).asInteger;
        ~setPerformanceGate.((1 - current).asInteger);
    };

    ~openProbeScope = {
        {
            try {
                s.scope(2);
            } { |error|
                ("Open Scope failed: " ++ error.asString).postln;
            };
        }.defer;
    };

    ~openProbeFreqScope = {
        {
            try {
                ~probeFreqScope = FreqScope.new;
            } { |error|
                ("Open FreqScope failed: " ++ error.asString).postln;
            };
        }.defer;
    };

    if(~regularUIOnly != true, { {
        (~basicProbeInstance == basicProbeInstance).if({
        ~probeWindow.notNil.if({
            ~probeWindow.close;
        });
        ~probeMonitorWindow.notNil.if({
            ~probeMonitorWindow.close;
        });
        ~probeVisualizerWindow.notNil.if({
            ~probeVisualizerWindow.close;
        });
        ~probeFxWindow.notNil.if({
            ~probeFxWindow.close;
        });
        ~probeMonitorLabels = nil;
        ~probeVisualLabels = nil;
        ~probeVisualViews = nil;

        ~probeWindow = Window("Probe Synth Controls", Rect(100, 100, 420, 650));
        ~probeControls = ();

        ~makeProbeSlider = { |label, key, minValue, maxValue, step = 0|
            var slider;
            slider = EZSlider(
                ~probeWindow,
                390@24,
                label,
                ControlSpec(minValue, maxValue, \lin, step, ~probeParams[key]),
                { |view| ~setProbeParam.(key, view.value); },
                ~probeParams[key]
            );
            ~probeControls[key] = slider;
            slider.view;
        };

        ~makeProbeFxSlider = { |label, key, minValue, maxValue, step = 0|
            var slider;
            slider = EZSlider(
                ~probeFxWindow,
                430@22,
                label,
                ControlSpec(minValue, maxValue, \lin, step, ~probeParams[key]),
                { |view| ~setProbeParam.(key, view.value); },
                ~probeParams[key]
            );
            ~probeControls[key] = slider;
            slider.view;
        };

        ~makeProbeToggle = { |label, key|
            var button;
            button = Button()
                .states_([
                    [label ++ ": OFF", Color.black, Color.gray(0.85)],
                    [label ++ ": ON", Color.white, Color(0.2, 0.45, 0.8)]
                ])
                .value_(~probeParams[key].asInteger)
                .action_({ |view| ~setProbeParam.(key, view.value); });
            ~probeControls[key] = button;
            button;
        };

        ~makePerformanceGateButton = {
            var button;
            button = Button()
                .states_([
                    ["Gate: OFF (space)", Color.black, Color.gray(0.85)],
                    ["Gate: ON (space)", Color.white, Color(0.2, 0.6, 0.25)]
                ])
                .value_(~probeParams[\performanceGate].asInteger)
                .action_({ ~togglePerformanceGate.(); });
            ~probeControls[\performanceGate] = button;
            button;
        };

        ~probeWindow.view.keyDownAction_({ |view, char, modifiers, unicode, keycode|
            ((unicode == 32) or: { keycode == 32 }).if({
                ~togglePerformanceGate.();
            });
        });

        ~probeWindow.layout = VLayout(
            StaticText().string_("Sample mapping probe synth controls"),
            StaticText().string_("Performance Gate starts OFF. Reset defaults returns it to OFF."),
            ~makePerformanceGateButton.(),
            ~makeProbeSlider.("crescendoTime", \crescendoTime, 0.0, 8.0, 0.001),
            ~makeProbeSlider.("decrescendoTime", \decrescendoTime, 0.0, 8.0, 0.001),
            ~makeProbeSlider.("freqLag", \freqLag, 0.0, 0.3, 0.001),
            ~makeProbeSlider.("ampLag", \ampLag, 0.0, 0.3, 0.001),
            ~makeProbeToggle.("portamento", \portamentoOn),
            ~makeProbeSlider.("portamentoTime", \portamentoTime, 0.0, 1.0, 0.001),
            ~makeProbeToggle.("softClip", \softClipOn),
            ~makeProbeSlider.("softClipDrive", \softClipDrive, 1.0, 20.0, 0.01),
            ~makeProbeSlider.("softClipMix", \softClipMix, 0.0, 1.0, 0.001),
            ~makeProbeToggle.("filter", \filterOn),
            ~makeProbeSlider.("filterCutoff", \filterCutoff, 80.0, 12000.0, 1.0),
            StaticText().string_("filterRq: low rq = sharper / more resonant"),
            ~makeProbeSlider.("filterRq", \filterRq, 0.05, 1.0, 0.001),
            ~makeProbeSlider.("filterMix", \filterMix, 0.0, 1.0, 0.001),
            ~makeProbeSlider.("filterLag", \filterLag, 0.0, 0.3, 0.001),
            ~makeProbeSlider.("outputLevel", \outputLevel, 0.0, 1.0, 0.001),
            ~makeProbeSlider.("ampMin", \ampMin, 0.0, 0.2, 0.001),
            ~makeProbeSlider.("ampMax", \ampMax, 0.01, 0.8, 0.001),
            Button()
                .states_([["Reset defaults", Color.black, Color.gray(0.85)]])
                .action_({
                    ~resetProbeParams.();
                    ~probeControls.keysValuesDo({ |key, control|
                        (key == \performanceGate).if({
                            control.value_(~probeParams[key].asInteger);
                        }, {
                            control.valueAction_(~probeParams[key]);
                        });
                    });
                })
        );
        ~probeWindow.front;

        ~probeFxWindow = Window("Probe Synth Additive / FX Controls", Rect(980, 100, 460, 760));
        ~probeFxWindow.layout = VLayout(
            StaticText().string_("Additive source"),
            ~makeProbeToggle.("additive", \additiveOn),
            ~makeProbeFxSlider.("additiveMix", \additiveMix, 0.0, 1.0, 0.001),
            ~makeProbeFxSlider.("additiveGain", \additiveGain, 0.0, 2.0, 0.001),
            StaticText().string_("Harmonics"),
            ~makeProbeFxSlider.("H1 fundamental", \harmonic1, 0.0, 1.0, 0.001),
            ~makeProbeFxSlider.("H2 octave", \harmonic2, 0.0, 1.0, 0.001),
            ~makeProbeFxSlider.("H3", \harmonic3, 0.0, 1.0, 0.001),
            ~makeProbeFxSlider.("H4", \harmonic4, 0.0, 1.0, 0.001),
            ~makeProbeFxSlider.("H5", \harmonic5, 0.0, 1.0, 0.001),
            ~makeProbeFxSlider.("H6", \harmonic6, 0.0, 1.0, 0.001),
            ~makeProbeFxSlider.("H7", \harmonic7, 0.0, 1.0, 0.001),
            ~makeProbeFxSlider.("H8", \harmonic8, 0.0, 1.0, 0.001),
            ~makeProbeFxSlider.("H9", \harmonic9, 0.0, 1.0, 0.001),
            ~makeProbeFxSlider.("H10", \harmonic10, 0.0, 1.0, 0.001),
            ~makeProbeFxSlider.("H11", \harmonic11, 0.0, 1.0, 0.001),
            ~makeProbeFxSlider.("H12", \harmonic12, 0.0, 1.0, 0.001),
            StaticText().string_("Filtered delay"),
            ~makeProbeToggle.("delay", \delayOn),
            ~makeProbeFxSlider.("delayMix", \delayMix, 0.0, 1.0, 0.001),
            ~makeProbeFxSlider.("delayTime", \delayTime, 0.02, 2.0, 0.001),
            ~makeProbeFxSlider.("delayFeedback", \delayFeedback, 0.0, 0.85, 0.001),
            ~makeProbeFxSlider.("delayFilterCutoff", \delayFilterCutoff, 100.0, 12000.0, 1.0),
            ~makeProbeFxSlider.("delayFilterRq", \delayFilterRq, 0.05, 1.0, 0.001),
            ~makeProbeFxSlider.("delayLag", \delayLag, 0.0, 0.3, 0.001),
            StaticText().string_("Reverb"),
            ~makeProbeToggle.("reverb", \reverbOn),
            ~makeProbeFxSlider.("reverbMix", \reverbMix, 0.0, 1.0, 0.001),
            ~makeProbeFxSlider.("reverbRoom", \reverbRoom, 0.0, 1.0, 0.001),
            ~makeProbeFxSlider.("reverbDamp", \reverbDamp, 0.0, 1.0, 0.001),
            Button()
                .states_([["Reset defaults", Color.black, Color.gray(0.85)]])
                .action_({
                    ~resetProbeParams.();
                    ~probeControls.keysValuesDo({ |key, control|
                        (key == \performanceGate).if({
                            control.value_(~probeParams[key].asInteger);
                        }, {
                            control.valueAction_(~probeParams[key]);
                        });
                    });
                })
        );
        ~probeFxWindow.front;

        ~probeMonitorWindow = Window("Probe Synth Monitor", Rect(540, 100, 420, 340));
        ~probeMonitorLabels = ();

        ~makeProbeMonitorLabel = { |key|
            var label;
            label = StaticText().string_("");
            ~probeMonitorLabels[key] = label;
            label;
        };

        ~probeMonitorWindow.layout = VLayout(
            StaticText().string_("Probe synth sound monitor"),
            HLayout(
                Button()
                    .states_([["Open Scope", Color.black, Color.gray(0.85)]])
                    .action_({ ~openProbeScope.(); }),
                Button()
                    .states_([["Open FreqScope", Color.black, Color.gray(0.85)]])
                    .action_({ ~openProbeFreqScope.(); })
            ),
            ~makeProbeMonitorLabel.(\freq),
            ~makeProbeMonitorLabel.(\amp),
            ~makeProbeMonitorLabel.(\gate),
            ~makeProbeMonitorLabel.(\level),
            ~makeProbeMonitorLabel.(\softClip),
            ~makeProbeMonitorLabel.(\filter),
            ~makeProbeMonitorLabel.(\filterFreq),
            ~makeProbeMonitorLabel.(\additive),
            ~makeProbeMonitorLabel.(\delay),
            ~makeProbeMonitorLabel.(\reverb)
        );
        ~refreshProbeMonitor.();
        ~probeMonitorWindow.front;

        ~probeVisualizerWindow = Window("Probe Synth Visualizer", Rect(540, 460, 650, 760));
        ~probeVisualLabels = ();
        ~probeVisualViews = ();

        ~makeProbeVisualLabel = { |key|
            var label;
            label = StaticText().string_("");
            ~probeVisualLabels[key] = label;
            label;
        };

        ~makeProbeVisualView = { |key, drawFunc|
            var view;
            view = UserView()
                .minHeight_(105)
                .background_(Color.gray(0.96))
                .drawFunc_({ |userView| drawFunc.(userView); });
            ~probeVisualViews[key] = view;
            view;
        };

        ~probeVisualizerWindow.layout = VLayout(
            StaticText().string_("Probe synth visual concepts"),
            StaticText().string_("Conceptual sound-design diagrams, not measurement scopes."),
            ~makeProbeVisualLabel.(\filter),
            ~makeProbeVisualView.(\filter, ~drawFilterVisual),
            ~makeProbeVisualLabel.(\harmonics),
            ~makeProbeVisualView.(\harmonics, ~drawHarmonicVisual),
            ~makeProbeVisualLabel.(\softClip),
            ~makeProbeVisualView.(\softClip, ~drawSoftClipVisual),
            ~makeProbeVisualLabel.(\pitch),
            ~makeProbeVisualView.(\pitch, ~drawPitchFollowVisual),
            ~makeProbeVisualLabel.(\delay),
            ~makeProbeVisualView.(\delay, ~drawDelayVisual)
        );
        ~refreshProbeVisuals.();
        ~probeVisualizerWindow.front;
        });
    }.defer; });

    OSCdef(\basicOscProbeMonitor, { |msg, time, addr, recvPort|
        var nodeID;
        ~debugProbeMonitor.if({
            msg.postln;
        });
        // SendReply arrives as [address, nodeID, replyID, followedFreq, followedAmp, env, filterFreq].
        (msg.size >= 7).if({
            nodeID = msg[1].asInteger;
            ((~basicReceiverSynth.isNil) or: {
                nodeID == ~basicReceiverSynth.nodeID
            }).if({
                ~probeMonitor[\followedFreq] = msg[3].asFloat;
                ~probeMonitor[\followedAmp] = msg[4].asFloat;
                ~probeMonitor[\performanceEnv] = msg[5].asFloat;
                ~probeMonitor[\filterFreq] = msg[6].asFloat;
                ~regularMonitorNotify.notNil.if({ ~regularMonitorNotify.(\basic, ~probeMonitor); });
                ~addProbeHistoryPoint.();
                ~updateProbeMonitor.();
            });
        }, {
            ~debugProbeMonitor.if({
                ["unexpected probe monitor msg", msg].postln;
            });
        });
    }, "/basicOscProbe/monitor");

    ~postControlEvent = { |msg, addr|
        var value;
        value = msg[1].asFloat;
        ~debugHandEvents.if({
            ["received", msg[0], value, "from", addr].postln;
        });
    };

    OSCdef(\handIndexX, { |msg, time, addr, recvPort|
        ~postControlEvent.(msg, addr);
    }, "/hand/0/index/x");

    OSCdef(\handIndexY, { |msg, time, addr, recvPort|
        ~postControlEvent.(msg, addr);
    }, "/hand/0/index/y");

    OSCdef(\handThumbX, { |msg, time, addr, recvPort|
        ~postControlEvent.(msg, addr);
    }, "/hand/0/thumb/x");

    OSCdef(\handThumbY, { |msg, time, addr, recvPort|
        ~postControlEvent.(msg, addr);
    }, "/hand/0/thumb/y");

    OSCdef(\handPinch, { |msg, time, addr, recvPort|
        ~postControlEvent.(msg, addr);
    }, "/hand/0/pinch");

    // Legacy sample probe value: kept for inspection, not Synth control.
    // Right hand index/y is inverted because image y has top = 0.
    OSCdef(\sampleRightIndexYInverted, { |msg, time, addr, recvPort|
        var value;
        value = msg[1].asFloat.clip(0, 1);
        ~debugSampleEvents.if({
            ["sample pitch norm legacy", value].postln;
        });
    }, "/sample/right/index/y_inverted");

    // Sample mapping only: Python computes the base pitch frequency.
    // Kept for inspection; Synth freq is controlled by final_freq below.
    OSCdef(\sampleRightPitchFreq, { |msg, time, addr, recvPort|
        var freq;
        freq = msg[1].asFloat.max(0);
        ~debugSampleEvents.if({
            ["sample pitch freq base", freq].postln;
        });
    }, "/sample/right/pitch/freq");

    // Sample mapping only: Python computes whether the octave gesture is active.
    // Kept for inspection; SuperCollider does not calculate pitch from it.
    OSCdef(\sampleRightPitchOctaveShift, { |msg, time, addr, recvPort|
        var value;
        value = msg[1].asFloat;
        ~debugSampleEvents.if({
            ["sample octave shift", value].postln;
        });
    }, "/sample/right/pitch/octave_shift");

    // Sample mapping only: Python computes the continuous pitch with octave.
    // Kept for inspection; Synth freq is controlled by final_freq below.
    OSCdef(\sampleRightPitchFreqWithOctave, { |msg, time, addr, recvPort|
        var freq;
        freq = msg[1].asFloat.max(0);
        ~debugSampleEvents.if({
            ["sample pitch freq with octave", freq].postln;
        });
    }, "/sample/right/pitch/freq_with_octave");

    // Sample mapping only: Python computes the quantized pitch candidate.
    // Kept for inspection; SuperCollider does not quantize pitch here.
    OSCdef(\sampleRightPitchQuantizedFreq, { |msg, time, addr, recvPort|
        var freq;
        freq = msg[1].asFloat.max(0);
        ~debugSampleEvents.if({
            ["sample pitch quantized freq", freq].postln;
        });
    }, "/sample/right/pitch/quantized_freq");

    // Sample mapping only: Python selects continuous or quantized final pitch.
    // SuperCollider uses the received final frequency directly for synthesis.
    OSCdef(\sampleRightPitchFinalFreq, { |msg, time, addr, recvPort|
        var freq;
        freq = msg[1].asFloat.max(0);
        ~probeMonitor[\targetFreq] = freq;
        ~basicReceiverSynth.notNil.if({
            ~basicReceiverSynth.set(\freq, freq);
        });
        ~updateProbeMonitor.();
        ~debugSampleEvents.if({
            ["sample pitch final freq", freq].postln;
        });
    }, "/sample/right/pitch/final_freq");

    // Sample mapping only: /sample/left/pinch -> amp.
    // Left hand pinch is used as an amplitude candidate in this example patch.
    // This confirms a sample patch mapping, not a platform-level volume rule.
    OSCdef(\sampleLeftPinch, { |msg, time, addr, recvPort|
        var value, amp, ampMin, ampMax;
        ~basicLastPinchAt = Main.elapsedTime;
        value = msg[1].asFloat.clip(0, 1);
        ampMin = ~probeParams[\ampMin].min(~probeParams[\ampMax]);
        ampMax = ~probeParams[\ampMin].max(~probeParams[\ampMax]);
        amp = value.linlin(0, 1, ampMin, ampMax);
        ~probeMonitor[\targetAmp] = amp;
        ~basicReceiverSynth.notNil.if({
            ~basicReceiverSynth.set(\amp, amp);
        });
        ~updateProbeMonitor.();
        ~debugSampleEvents.if({
            ["sample amp", value, amp].postln;
        });
    }, "/sample/left/pinch");

    // Preserve the manual performance gate; resume when left-hand data returns.
    ~basicLastPinchAt = nil;
    ~releaseBasicInput = {
        ~basicLastPinchAt = nil;
        ~probeMonitor[\targetAmp] = 0;
        ~basicReceiverSynth.notNil.if({ ~basicReceiverSynth.set(\amp, 0); });
        ~updateProbeMonitor.();
    };
    OSCdef(\basicProbePanic, { ~releaseBasicInput.(); }, "/sample/panic");
    ~basicInputWatchdog = Routine({
        loop {
            (~basicLastPinchAt.notNil).if({
                ((Main.elapsedTime - ~basicLastPinchAt) >= 1.0).if({
                    ~releaseBasicInput.();
                });
            });
            0.1.wait;
        };
    }).play(SystemClock);

    // Shared, intentionally small probe-switch protocol.  It is safe to call
    // more than once and leaves this receiver ready to be evaluated again.
    ~activeProbeCleanup = {
        var windows, oscdefKeys;
        ~basicInputWatchdog.notNil.if({ ~basicInputWatchdog.stop; });
        ~basicInputWatchdog = nil;
        ~basicProbeInstance = (~basicProbeInstance ? 0) + 1;
        ~basicReceiverSynth.notNil.if({
            ~basicReceiverSynth.free;
        });
        ~basicReceiverSynth = nil;

        oscdefKeys = [
            \basicOscProbeMonitor,
            \handIndexX,
            \handIndexY,
            \handThumbX,
            \handThumbY,
            \handPinch,
            \sampleRightIndexYInverted,
            \sampleRightPitchFreq,
            \sampleRightPitchOctaveShift,
            \sampleRightPitchFreqWithOctave,
            \sampleRightPitchQuantizedFreq,
            \sampleRightPitchFinalFreq,
            \basicProbePanic,
            \sampleLeftPinch
        ];
        oscdefKeys.do({ |key|
            try {
                OSCdef(key).free;
            } { |error| };
        });

        windows = [
            ~probeWindow,
            ~probeFxWindow,
            ~probeMonitorWindow,
            ~probeVisualizerWindow
        ];
        windows.do({ |window|
            window.notNil.if({
                try {
                    window.close;
                } { |error| };
            });
        });
        ~probeWindow = nil;
        ~probeFxWindow = nil;
        ~probeMonitorWindow = nil;
        ~probeVisualizerWindow = nil;
        ~probeFreqScope.notNil.if({
            try {
                ~probeFreqScope.kill;
            } { |error| };
        });
        ~probeFreqScope = nil;
        ~probeControls = nil;
        ~probeMonitorLabels = nil;
        ~probeVisualLabels = nil;
        ~probeVisualViews = nil;
        (~activeProbeName == \basicReceiver).if({
            ~activeProbeName = nil;
        });
    };
    ~activeProbeName = \basicReceiver;

    ("Listening for generic hand control events on port " ++ NetAddr.langPort).postln;
    "Listening for sample mapping events that control the probe synth.".postln;
    "Probe synth controls are available in the SuperCollider UI window.".postln;
    "Probe synth additive / FX controls are available in a separate UI window.".postln;
    "Probe synth monitor is available with Scope and FreqScope buttons.".postln;
    "Probe synth visualizer is available for conceptual tone-shaping diagrams.".postln;
    "Set ~debugHandEvents or ~debugSampleEvents to true for per-event logs.".postln;
    });
});
)

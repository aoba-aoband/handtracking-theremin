/* Shared stereo instrument FX. Koala/input never enters these buses.
   Vanilla SC UGens only. See docs/effects-design.md for sources and limits. */
(
~regularDefineDSP = {
    SynthDef(\regularTremolo, { |in=0, out=0, on=0, rate=5, depth=0.5, wave=0|
        var signal, lfo, amount;
        signal = In.ar(in, 2);
        lfo = Select.kr(wave.clip(0, 2), [SinOsc.kr(Lag.kr(rate, 0.03)), LFTri.kr(Lag.kr(rate, 0.03)), LFPulse.kr(Lag.kr(rate, 0.03)).range(-1, 1)]);
        lfo = Lag.kr(lfo, 0.003);
        amount = Lag.kr(on.clip(0, 1) * depth.clip(0, 2), 0.03);
        Out.ar(out, signal * (1 - (amount * (lfo + 1) * 0.5)));
    }).add;
    SynthDef(\regularDistortion, { |in=0, out=0, on=0, drive=2, tone=8000, level=0.5, mix=1|
        var signal, wet, blend, gain;
        signal = In.ar(in, 2);
        gain = Lag.kr(drive.clip(1, 80), 0.03);
        wet = (signal * gain).tanh / gain.tanh;
        wet = LPF.ar(LeakDC.ar(wet), Lag.kr(tone.clip(100, 18000).min(SampleRate.ir * 0.4), 0.03)) * Lag.kr(level, 0.03);
        blend = Lag.kr(on.clip(0, 1) * mix.clip(0, 1), 0.03);
        Out.ar(out, (signal * (1 - blend)) + (wet * blend));
    }).add;
    SynthDef(\regularFuzz, { |in=0, out=0, on=0, drive=8, tone=4000, level=0.4, mix=1|
        var signal, wet, blend;
        signal = In.ar(in, 2);
        wet = LPF.ar(signal, tone.clip(100, 18000).min(SampleRate.ir * 0.2));
        wet = ((wet * Lag.kr(drive.clip(1, 160), 0.03)) + 0.35).tanh.clip(-0.55, 0.85);
        wet = LPF.ar(LeakDC.ar(wet), Lag.kr(tone.clip(100, 18000).min(SampleRate.ir * 0.4), 0.03)) * Lag.kr(level, 0.03);
        blend = Lag.kr(on.clip(0, 1) * mix.clip(0, 1), 0.03);
        Out.ar(out, (signal * (1 - blend)) + (wet * blend));
    }).add;
    SynthDef(\regularDelay, { |in=0, out=0, on=0, mix=0, time=0.25, feedback=0.25, filterCutoff=4000, filterRq=0.5, lag=0.05, bufferL=0, bufferR=1|
        var signal, feed, wet, blend, phase, readPhase, delayInput;
        signal = In.ar(in, 2);
        feed = Lag.kr(on.clip(0, 1), 0.03);
        phase = Phasor.ar(0, 1, 0, BufFrames.ir(bufferL));
        readPhase = phase - (Lag.kr(time.clip(0.02, 2), lag.max(0.005)) * SampleRate.ir);
        wet = BufRd.ar(1, [bufferL, bufferR], readPhase, 1, 4);
        wet = RLPF.ar(wet, Lag.kr(filterCutoff.clip(100, 12000), lag.max(0.005)), filterRq.clip(0.05, 1));
        delayInput = (signal * feed) + (LeakDC.ar(wet).clip2(2) * feedback.clip(0, 0.85));
        BufWr.ar(delayInput[0], bufferL, phase, 1);
        BufWr.ar(delayInput[1], bufferR, phase, 1);
        blend = Lag.kr(mix.clip(0, 1), 0.03);
        // Off stops new wet input and restores dry; existing feedback decays.
        Out.ar(out, (signal * (1 - (feed * blend))) + (wet * blend));
    }).add;
    SynthDef(\regularReverb, { |in=0, out=0, on=0, mix=0, room=0.4, damp=0.5|
        var signal, feed, wet, blend;
        signal = In.ar(in, 2);
        feed = Lag.kr(on.clip(0, 1), 0.03);
        wet = FreeVerb2.ar(signal[0] * feed, signal[1] * feed, 1, room.clip(0, 1), damp.clip(0, 1));
        blend = Lag.kr(mix.clip(0, 1), 0.03);
        Out.ar(out, (signal * (1 - (feed * blend))) + (wet * blend));
    }).add;
    SynthDef(\regularThru, { |out=0, on=0, level=1|
        Out.ar(out, SoundIn.ar([0, 1]) * Lag.kr(on.clip(0, 1) * level.clip(0, 2), 0.03));
    }).add;
    SynthDef(\regularMaster, { |inA=0, inB=0, thru=0, blend=0, mute=1, testMute=0|
        var cross, instrument, direct, signal;
        cross = Lag.kr(blend.clip(0, 1), 0.02);
        instrument = (In.ar(inA, 2) * (1-cross)) + (In.ar(inB, 2) * cross);
        direct = In.ar(thru, 2);
        // Final DC removal / hard peak protection, no lookahead.
        // PANIC is after all processing, including DC / final peak protection.
        signal = LeakDC.ar(instrument + direct);
        signal = signal.clip2(0.98);
        Out.ar(0, signal * (1-mute.clip(0, 1)) * (1-testMute.clip(0, 1)));
    }).add;
};
~regularFXSymbols = (tremolo: \regularTremolo, distortion: \regularDistortion, fuzz: \regularFuzz, delay: \regularDelay, reverb: \regularReverb);
~regularFXOrder = ~regularFXOrder ? [\tremolo, \distortion, \fuzz, \delay, \reverb];
~regularFX = ~regularFX ? ();
~regularFXSpecs.keysValuesDo({ |effect, specs|
    ~regularFX[effect].isNil.if({ ~regularFX[effect] = (); specs.keysValuesDo({ |key, spec| ~regularFX[effect][key] = spec[3]; }); });
});
~regularMod = ();
~regularFXChains = List.new;
~regularThruOn = 0;
~regularThruLevel = 1;
~regularMuted = true;
~regularEffectiveFX = { |effect|
    var values, modulation, age;
    values = ~regularFX[effect].copy;
    modulation = ~regularMod[effect];
    modulation.notNil.if({
        age = Main.elapsedTime - modulation[\at];
        values[modulation[\target]] = (age < 0.6).if({ modulation[\value] }, {
            (modulation[\target] == \rate).if({ values[\rate] }, { ~regularFXSpecs[effect][modulation[\target]][0] });
        });
        [\tremolo, \vibrato].includes(effect).if({
            (modulation[\target] == \rate).if({ values[\depth] = values[\depth] * ((age < 0.6).if({ modulation[\presence] }, { 0 })); });
        });
        [\distortion, \fuzz].includes(effect).if({
            // Minimum drive alone is still coloured (especially biased fuzz).
            // Hand loss fades the wet path as well as returning drive to minimum.
            values[\mix] = values[\mix] * ((age < 0.6).if({ modulation[\presence] }, { 0 }));
        });
    });
    values;
};
~regularApplyFX = { |effect|
    var pairs, values, synth;
    values = ~regularEffectiveFX.(effect);
    pairs = List.new; values.keysValuesDo({ |key, value| pairs.add(key); pairs.add(value); });
    (effect == \vibrato).if({
        ~regularProbe.notNil.if({
            synth = ~regularDescriptors[~regularProbe][\synth].value;
            synth.notNil.if({ synth.set(\vibratoOn, values[\on], \vibratoRate, values[\rate], \vibratoDepth, values[\depth], \vibratoWave, values[\wave]); });
        });
    }, {
        ~regularFXChains.do({ |chain| (chain[\nodes][effect].notNil and: { (effect != \delay) or: { chain[\ready] } }).if({ chain[\nodes][effect].set(*pairs.asArray); }); });
    });
};
~regularNewChain = { |order|
    var chain, input, token;
    token = ~regularGeneration;
    chain = (group: Group.after(~regularSourceGroup), nodes: (), buses: List.new, buffers: List.new, alive: true, ready: false);
    input = ~regularInstrumentBus.index;
    order.do({ |effect|
        var output, stage;
        output = Bus.audio(s, 2); chain[\buses].add(output);
        stage = Group.tail(chain[\group]);
        (effect == \delay).if({
            var left, right, frames, args;
            frames = (s.sampleRate * 2).ceil.asInteger.nextPowerOfTwo;
            chain[\nodes][effect] = Synth.basicNew(~regularFXSymbols[effect], s);
            left = Buffer(s, frames, 1); right = Buffer(s, frames, 1);
            chain[\buffers].add(left); chain[\buffers].add(right);
            args = [\in, input, \out, output.index, \bufferL, left.bufnum, \bufferR, right.bufnum];
            ~regularEffectiveFX.(effect).keysValuesDo({ |key, value| args = args ++ [key, value]; });
            // Server-side completion messages create Delay only after both
            // mono buffers exist. No stale language boot callback can create it.
            s.listSendMsg(left.allocMsg(right.allocMsg(chain[\nodes][effect].newMsg(stage, args, \addToTail))));
        }, {
            chain[\nodes][effect] = Synth.tail(stage, ~regularFXSymbols[effect], [\in, input, \out, output.index]);
        });
        input = output.index;
    });
    chain[\output] = input;
    ~regularFXChains.add(chain);
    ~regularFXSpecs.keys.do({ |effect| ~regularApplyFX.(effect); });
    AppClock.sched(0.03, {
        ((token == ~regularGeneration) and: { chain[\alive] }).if({ chain[\ready] = true; ~regularApplyFX.(\delay); }); nil;
    });
    chain;
};
~regularFreeChain = { |chain, immediate = false|
    chain.notNil.if({
        var token;
        token = ~regularGeneration; chain[\alive] = false; chain[\group].free;
        ~regularFXChains.remove(chain);
        immediate.if({ chain[\buses].do(_.free); chain[\buffers].do(_.free); }, {
            AppClock.sched(0.1, {
                (token == ~regularGeneration).if({ chain[\buses].do(_.free); chain[\buffers].do(_.free); }); nil;
            });
        });
    });
};
~regularCreateGraph = {
    ~regularInstrumentBus = Bus.audio(s, 2);
    ~regularThruBus = Bus.audio(s, 2);
    ~regularMonitorBus = Bus.control(s, 17);
    ~regularSourceGroup = Group.head(s);
    ~regularOutputGroup = Group.after(~regularSourceGroup);
    ~regularChain = ~regularNewChain.(~regularFXOrder);
    ~regularMaster = Synth.tail(~regularOutputGroup, \regularMaster, [\inA, ~regularChain[\output], \inB, ~regularChain[\output], \thru, ~regularThruBus.index, \mute, 1]);
    (s.options.numInputBusChannels >= 2).if({
        ~regularThruSynth = Synth.head(~regularOutputGroup, \regularThru, [\out, ~regularThruBus.index, \on, 0, \level, ~regularThruLevel]);
    });
    ~regularMuted = true;
};
~regularReorder = { |order, done|
    var old, fresh, token;
    token = ~regularGeneration;
    old = ~regularChain;
    fresh = ~regularNewChain.(order);
    ~regularFXOrder = order;
    ~regularMaster.set(\inA, old[\output], \inB, fresh[\output], \blend, 1);
    ~regularChain = fresh;
    ~regularOrderRoutine = Routine({
        0.16.wait;
        (token == ~regularGeneration).if({
            ~regularMaster.set(\inA, fresh[\output], \inB, fresh[\output], \blend, 0);
            ~regularFreeChain.(old);
            done.value;
        });
    }).play(AppClock);
};
~regularClearFX = {
    var old, fresh;
    ~regularMaster.notNil.if({
        old = ~regularFXChains.copy;
        fresh = ~regularNewChain.(~regularFXOrder);
        ~regularChain = fresh;
        ~regularMaster.set(\inA, fresh[\output], \inB, fresh[\output], \blend, 0);
        old.do({ |chain| ~regularFreeChain.(chain); });
    });
};
~regularFreeGraph = {
    ~regularOrderRoutine.notNil.if({ ~regularOrderRoutine.stop; });
    ~regularFXChains.copy.do({ |chain| ~regularFreeChain.(chain, true); });
    [~regularSourceGroup, ~regularOutputGroup].do({ |group| group.notNil.if({ group.free; }); });
    [~regularInstrumentBus, ~regularThruBus, ~regularMonitorBus].do({ |bus| bus.notNil.if({ bus.free; }); });
    ~regularMaster = nil; ~regularThruSynth = nil; ~regularSourceGroup = nil;
    ~regularInstrumentBus = nil; ~regularThruBus = nil; ~regularMonitorBus = nil; ~regularChain = nil;
};
)

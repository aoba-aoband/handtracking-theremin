/* Regular UI session. Device enumeration is available before audio-server boot. */
(
var root;
root = thisProcess.nowExecutingPath.standardizePath.dirname;
~regularBridgeCleanup.notNil.if({ ~regularBridgeCleanup.(); });
~regularGeneration = (~regularGeneration ? 0) + 1;
~regularSpecs = (root +/+ "regular_specs.scd").load;
(root +/+ "regular_effect_specs.scd").load;
~regularProbe = nil; ~regularAddress = nil; ~regularSeen = Dictionary.new; ~regularBusy = nil;
~regularLastContact = Main.elapsedTime; ~regularSaved = (); ~regularInitializing = false;
~regularAudioStatus = "unconfigured"; ~regularAudioError = "";
~regularDevices = (input: [], output: []);
~regularDescriptors = (
    basic: (filename: "basic_receiver.scd", activeName: \basicReceiver,
        params: { ~probeParams }, synth: { ~basicReceiverSynth },
        set: { |key, value| ~setProbeParam.(key, value); }, release: { ~releaseBasicInput.(); },
        scope: { ~openProbeScope.(); }, spectrum: { ~openProbeFreqScope.(); }),
    subtractive: (filename: "subtractive_probe.scd", activeName: \subtractiveProbe,
        params: { ~subtractiveParams }, synth: { ~subtractiveSynth },
        set: { |key, value|
            case
            { [\toneMinCutoff, \toneMaxCutoff].includes(key) } { ~setSubtractiveToneRange.(key, value); }
            { key == \toneInvert } { ~setSubtractiveToneInvert.(value); }
            { true } { ~setSubtractiveParam.(key, value); };
        }, release: { ~releaseSubtractiveInput.(); },
        scope: { ~openSubtractiveScope.(); }, spectrum: { ~openSubtractiveFreqScope.(); })
);
~regularLegacyFX = (
    delayOn: [\delay, \on], delayMix: [\delay, \mix], delayTime: [\delay, \time],
    delayFeedback: [\delay, \feedback], delayFilterCutoff: [\delay, \filterCutoff],
    delayFilterRq: [\delay, \filterRq], delayLag: [\delay, \lag],
    reverbOn: [\reverb, \on], reverbMix: [\reverb, \mix], reverbRoom: [\reverb, \room], reverbDamp: [\reverb, \damp]
);
(root +/+ "regular_engine.scd").load;
~regularAudioReply = {
    ~regularAddress.notNil.if({
        ~regularAddress.sendMsg('/regular/audio', ~regularAudioStatus, ~regularAudioError, ~regularGeneration,
            s.avgCPU ? 0, s.peakCPU ? 0, s.options.numInputBusChannels, s.options.numOutputBusChannels, s.sampleRate ? 0);
    });
};
~regularEnumerate = {
    "Audio Setup: enumerating SC input/output devices".postln;
    try {
        ~regularDevices[\input] = ServerOptions.inDevices;
        ~regularDevices[\output] = ServerOptions.outDevices;
        "Audio Setup: enumeration complete".postln;
        ~regularAddress.notNil.if({
            ~regularAddress.sendMsg(*(['/regular/devices', "input"] ++ ~regularDevices[\input]));
            ~regularAddress.sendMsg(*(['/regular/devices', "output"] ++ ~regularDevices[\output]));
        });
    } { |error| ~regularAudioError = "SC device enumeration failed: " ++ error.asString; ~regularAudioReply.(); };
};
~regularState = {
    var pairs, params;
    (~regularAddress.notNil and: { ~regularProbe.notNil }).if({
        params = ~regularDescriptors[~regularProbe][\params].value;
        (~regularProbe == \basic).if({ ~regularLegacyFX.keysValuesDo({ |key, pair| params[key] = ~regularFX[pair[0]][pair[1]]; }); });
        pairs = List.new; params.keysValuesDo({ |key, value| pairs.add(key.asString); pairs.add(value); });
        ~regularAddress.sendMsg(*(['/regular/state', ~regularProbe.asString] ++ pairs.asArray));
    });
    ~regularAddress.notNil.if({
        pairs = List.new;
        ~regularFX.keysValuesDo({ |fx, values| values.keysValuesDo({ |key, value| pairs.add(fx.asString ++ "." ++ key.asString); pairs.add(value); }); });
        ~regularAddress.sendMsg(*(['/regular/fx_state'] ++ pairs.asArray));
        ~regularAddress.sendMsg(*(['/regular/order'] ++ ~regularFXOrder.collect(_.asString)));
    });
    ~regularAudioReply.();
};
~regularMonitorNotify = { |probe, monitor|
    var pairs;
    (~regularAddress.notNil and: { probe == ~regularProbe }).if({
        pairs = List.new; monitor.keysValuesDo({ |key, value| pairs.add(key.asString); pairs.add(value); });
        ~regularAddress.sendMsg(*(['/regular/monitor', probe.asString] ++ pairs.asArray));
    });
};
~regularMute = {
    var desc, wasMuted;
    wasMuted = ~regularMuted; ~regularMuted = true;
    ~regularMaster.notNil.if({ ~regularMaster.set(\mute, 1); });
    ~regularProbe.notNil.if({
        desc = ~regularDescriptors[~regularProbe];
        desc[\set].value(\performanceGate, 0); desc[\release].value;
        desc[\synth].value.notNil.if({ desc[\synth].value.set(\uiMute, 1); });
    });
    (wasMuted == false).if({ ~regularClearFX.(); });
};
~regularAck = { |id|
    var parts;
    parts = id.split($:);
    ~regularSeen[parts[0]] = (~regularSeen[parts[0]] ? 0).max(parts[1].asInteger);
    ~regularBusy = nil;
    ~regularAddress.notNil.if({ ~regularAddress.sendMsg('/regular/ack', id); });
    ~regularState.();
};
~regularSetFX = { |effect, key, value|
    var spec;
    spec = ~regularFXSpecs[effect];
    spec.notNil.if({ spec = spec[key]; spec.notNil.if({
        value = value.asFloat.clip(spec[0], spec[1]);
        (spec[2] > 0).if({ value = value.round(spec[2]); });
        ~regularFX[effect][key] = value; ~regularApplyFX.(effect);
    }); });
};
~regularSet = { |probe, key, value|
    var spec, desc, pair;
    spec = ~regularSpecs[probe][key];
    spec.notNil.if({
        value = value.asFloat.clip(spec[0], spec[1]);
        (spec[2] > 0).if({ value = value.round(spec[2]); });
        desc = ~regularDescriptors[probe];
        (probe == ~regularProbe).if({ desc[\set].value(key, value); }, {
            ~regularSaved[probe].isNil.if({ ~regularSaved[probe] = (); }); ~regularSaved[probe][key] = value;
        });
        (probe == \basic).if({ pair = ~regularLegacyFX[key]; pair.notNil.if({ ~regularSetFX.(pair[0], pair[1], value); }); });
    });
};
~regularSelect = { |probe, done|
    var desc, token;
    token = ~regularGeneration;
    (probe == ~regularProbe).if({ done.value; }, {
        ("Regular: selecting " ++ probe.asString).postln;
        ~regularMute.();
        ~regularProbe.notNil.if({ ~regularSaved[~regularProbe] = ~regularDescriptors[~regularProbe][\params].value.copy; });
        ~regularProbe = nil; desc = ~regularDescriptors[probe]; ~regularUIOnly = true;
        (root +/+ desc[\filename]).load;
        ~regularSelectRoutine = Routine({
            var count, synth;
            count = 0;
            while { (~activeProbeName != desc[\activeName]) and: { count < 200 } and: { token == ~regularGeneration } } { 0.1.wait; count = count + 1; };
            ((~activeProbeName == desc[\activeName]) and: { token == ~regularGeneration }).if({
                ~regularProbe = probe; synth = desc[\synth].value;
                synth.moveToHead(~regularSourceGroup); synth.set(\out, ~regularInstrumentBus.index, \sharedFX, 1,
                    \monitorBus, ~regularMonitorBus.index, \monitorGeneration, ~regularGeneration);
                ~regularSaved[probe].notNil.if({ ~regularSaved[probe].keysValuesDo({ |key, value|
                    ((key != \performanceGate) and: { ~regularSpecs[probe][key].notNil } and: { ~regularLegacyFX[key].isNil }).if({ ~regularSet.(probe, key, value); });
                }); });
                ~regularApplyFX.(\vibrato); ~regularMute.(); ~regularUIOnly = false; done.value;
            }, { (token == ~regularGeneration).if({
                ~regularAudioStatus = "failed"; ~regularAudioError = "Probe creation failed; inspect SC log"; ~regularBusy = nil; ~regularAudioReply.();
            }); });
        }).play(AppClock);
    });
};
~regularConfigure = { |input, output, rate|
    var token, selected, valid;
    "Audio Setup: applying configuration".postln;
    ~regularEnumerate.();
    valid = (["__NONE__", "__DEFAULT__"].includesEqual(input) or: { ~regularDevices[\input].includesEqual(input) })
        and: { (output == "__DEFAULT__") or: { ~regularDevices[\output].includesEqual(output) } };
    valid.if({
        ~regularMute.(); selected = ~regularProbe ? \basic;
        ~regularProbe.notNil.if({ ~regularSaved[~regularProbe] = ~regularDescriptors[~regularProbe][\params].value.copy; });
        ~regularGeneration = ~regularGeneration + 1; token = ~regularGeneration;
        [~regularBootRoutine, ~regularSelectRoutine, ~regularOrderRoutine].do({ |routine| routine.notNil.if({ routine.stop; }); });
        ~basicProbeInstance = (~basicProbeInstance ? 0) + 1; ~subtractiveProbeInstance = (~subtractiveProbeInstance ? 0) + 1;
        ~activeProbeCleanup.notNil.if({ ~activeProbeCleanup.(); });
        ~activeProbeCleanup = nil; ~activeProbeName = nil; ~regularProbe = nil;
        ~regularFreeGraph.(); ~regularMod = (); ~regularThruOn = 0;
        ~regularAudioStatus = "booting"; ~regularAudioError = ""; ~regularInitializing = true; ~regularAudioReply.();
        ~regularBootRoutine = Routine({
            var count;
            "Audio Setup: waiting for old audio process".postln;
            s.serverRunning.if({ s.quit(watchShutDown: false); });
            count = 0;
            // serverRunning becomes false before scsynth actually exits. Wait
            // for the owned process too; never overlap boot with the old PID.
            while { (s.serverRunning or: { s.applicationRunning }) and: { count < 160 } and: { token == ~regularGeneration } } { 0.05.wait; count = count + 1; };
            ((token == ~regularGeneration) and: { count < 160 }).if({
                0.3.wait;
                "Audio Setup: booting configured server".postln;
                s.options.inDevice = (input == "__DEFAULT__" or: { input == "__NONE__" }).if({ nil }, { input });
                s.options.outDevice = (output == "__DEFAULT__").if({ nil }, { output });
                s.options.numInputBusChannels = (input == "__NONE__").if({ 0 }, { 2 }); s.options.numOutputBusChannels = 2;
                s.options.sampleRate = ((thisProcess.platform.name == \osx) and: { input != "__NONE__" } and: { input != output }).if({ nil }, { (rate <= 0).if({ nil }, { rate }) });
                s.options.memSize = s.options.memSize.max(32768);
                s.boot; count = 0;
                while { s.serverRunning.not and: { count < 400 } and: { token == ~regularGeneration } } { 0.05.wait; count = count + 1; };
                (token == ~regularGeneration).if({ s.serverRunning.if({
                    ~regularDefineDSP.(); s.sync; ~regularCreateGraph.(); s.sync;
                    ~regularSelect.(selected, { (token == ~regularGeneration).if({
                        ~regularAudioStatus = "ready"; ~regularInitializing = false; ~regularAudioReply.();
                    }); });
                }, {
                    ~regularAudioStatus = "failed"; ~regularInitializing = false;
                    ~regularAudioError = "Audio boot failed. Check log: missing/busy device, incompatible Windows APIs or sample-rate mismatch. On macOS check Audio MIDI Setup / Aggregate Device. Reconfigure to retry.";
                    ~regularAudioReply.();
                }); });
            }, {
                (token == ~regularGeneration).if({
                    ~regularAudioStatus = "failed"; ~regularInitializing = false;
                    ~regularAudioError = "The old audio process did not stop. Audio remains muted; inspect the log before retrying.";
                    ~regularAudioReply.();
                });
            });
        }).play(AppClock);
    }, { ~regularMute.(); ~regularAudioStatus = "missing-device"; ~regularAudioError = "Selected device unavailable; explicit selection required"; ~regularAudioReply.(); });
};
OSCdef(\regularRequest, { |msg, time, addr| {
    var id, operation, probe, key, value, parts, order, valid;
    (addr.ip == "127.0.0.1").if({
        ~regularAddress = NetAddr(addr.ip, msg[1].asInteger); ~regularLastContact = Main.elapsedTime;
        id = msg[2].asString; parts = id.split($:); operation = msg[3].asString;
        ((~regularSeen[parts[0]] ? 0) >= parts[1].asInteger).if({ ~regularAddress.sendMsg('/regular/ack', id); }, {
            ~regularBusy.isNil.if({
                ~regularBusy = id;
                case
                { operation == "devices" } { ~regularEnumerate.(); ~regularAck.(id); }
                { operation == "audio" } { ~regularConfigure.(msg[4].asString, msg[5].asString, msg[6].asFloat); ~regularAck.(id); }
                { operation == "select" } {
                    probe = msg[4].asSymbol;
                    (~regularAudioStatus != "ready").if({ ~regularBusy = nil; }, {
                        ~regularDescriptors[probe].notNil.if({ ~regularSelect.(probe, { ~regularAck.(id); }); }, { ~regularAck.(id); });
                    });
                }
                { operation == "set" } {
                    probe = msg[4].asSymbol; key = msg[5].asSymbol; value = msg[6].asFloat;
                    ~regularSpecs[probe].notNil.if({
                        ~regularSet.(probe, key, value);
                        ((key == \performanceGate) and: { value >= 1 } and: { probe == ~regularProbe } and: { ~regularAudioStatus == "ready" }).if({
                            ~regularDescriptors[probe][\synth].value.set(\uiMute, 0); ~regularMaster.set(\mute, 0); ~regularMuted = false;
                        });
                    }); ~regularAck.(id);
                }
                { operation == "restore" } {
                    probe = msg[4].asSymbol; ~regularMute.();
                    ~regularSpecs[probe].notNil.if({ msg.copyRange(5, msg.size-1).clump(2).do({ |pair|
                        (pair[0].asSymbol != \performanceGate).if({ ~regularSet.(probe, pair[0].asSymbol, pair[1]); });
                    }); }); ~regularAck.(id);
                }
                { operation == "fx" } { ~regularSetFX.(msg[4].asSymbol, msg[5].asSymbol, msg[6]); ~regularAck.(id); }
                { operation == "mod_source" } {
                    probe = msg[4].asSymbol; key = msg[5].asSymbol;
                    ~regularFXSpecs[probe].notNil.if({ ~regularFXSpecs[probe][key].notNil.if({
                        (msg[6].asInteger == 0).if({ ~regularMod.removeAt(probe); }, {
                            ~regularMod[probe] = (target: key, value: ~regularFXSpecs[probe][key][0], presence: 0, at: 0);
                        }); ~regularApplyFX.(probe);
                    }); }); ~regularAck.(id);
                }
                { operation == "order" } {
                    order = msg.copyRange(4, msg.size-1).collect(_.asSymbol);
                    valid = (order.size == 5) and: { order.asSet == ~regularFXSymbols.keys.asSet };
                    (valid and: { ~regularAudioStatus == "ready" }).if({ ~regularReorder.(order, { ~regularAck.(id); }); }, { ~regularAck.(id); });
                }
                { operation == "thru" } {
                    ~regularThruOn = (s.options.numInputBusChannels >= 2).if({ msg[4].asFloat.clip(0, 1) }, { 0 });
                    ~regularThruLevel = msg[5].asFloat.clip(0, 2);
                    ~regularThruSynth.notNil.if({ ~regularThruSynth.set(\on, ~regularThruOn, \level, ~regularThruLevel); }); ~regularAck.(id);
                }
                { operation == "panic" } { ~regularMute.(); ~regularAck.(id); }
                { operation == "inspect" } {
                    var token, destination, source;
                    token = ~regularGeneration; destination = ~regularAddress;
                    destination.sendMsg('/regular/inspect', "generation", token, "serverPort", s.addr.port,
                        "chainCount", ~regularFXChains.size, "handlerCount", OSCdef.all.size,
                        "thruNode", (~regularThruSynth.notNil).if({ ~regularThruSynth.nodeID }, { -1 }));
                    ~regularProbe.notNil.if({
                        source = ~regularDescriptors[~regularProbe][\synth].value;
                        destination.sendMsg('/regular/inspect', "sourceUGens", SynthDescLib.global.at(source.defName).def.children.collect({ |ugen| ugen.class.name.asString }).asSet.asArray.join(","));
                        [\out, \sharedFX, \vibratoRate, \vibratoDepth, \performanceGate].do({ |key|
                            source.get(key, { |value| (token == ~regularGeneration).if({ destination.sendMsg('/regular/inspect', "source." ++ key.asString, value); }); });
                        });
                    });
                    ~regularMaster.notNil.if({ [\mute, \inA, \inB].do({ |key|
                        ~regularMaster.get(key, { |value| (token == ~regularGeneration).if({ destination.sendMsg('/regular/inspect', "master." ++ key.asString, value); }); });
                    }); });
                    ~regularChain.notNil.if({ ~regularChain[\nodes].keysValuesDo({ |effect, node|
                        [\in, \out].do({ |key| node.get(key, { |value|
                            (token == ~regularGeneration).if({ destination.sendMsg('/regular/inspect', effect.asString ++ "." ++ key.asString, value); });
                        }); });
                    }); });
                    ~regularAck.(id);
                }
                { ["scope", "spectrum"].includesEqual(operation) } { ~regularProbe.notNil.if({ ~regularDescriptors[~regularProbe][operation.asSymbol].value; }); ~regularAck.(id); }
                { true } { (~regularDevices[\output].isEmpty).if({ ~regularEnumerate.(); }); ~regularAck.(id); };
            });
        });
    });
}.defer; }, '/regular/request');
OSCdef(\regularModulation, { |msg, time, addr|
    var effect, key, spec;
    (addr.ip == "127.0.0.1").if({
        effect = msg[1].asSymbol; key = msg[2].asSymbol; spec = ~regularFXSpecs[effect];
        spec.notNil.if({ spec = spec[key]; spec.notNil.if({
            ~regularMod[effect] = (target: key, value: msg[3].asFloat.clip(spec[0], spec[1]), presence: msg[4].asFloat.clip(0, 1), at: Main.elapsedTime);
            ~regularApplyFX.(effect);
        }); });
    });
}, '/regular/mod');
OSCdef(\regularPanic, { { ~regularMute.(); }.defer; }, '/regular/panic');
OSCdef(\regularSamplePanic, { { ~regularMute.(); }.defer; }, '/sample/panic');
OSCdef(\regularControlMonitor, { |msg, time, addr|
    var handler, values;
    ((addr == s.addr) and: { ~regularAudioStatus == "ready" } and: { ~regularMonitorBus.notNil }
        and: { msg[1] == ~regularMonitorBus.index } and: { msg[3] == ~regularGeneration } and: { ~regularProbe.notNil }).if({
        handler = (~regularProbe == \basic).if({ \basicOscProbeMonitor }, { \subtractiveProbeMonitor });
        values = msg.copyRange(4, msg.size-1);
        (~regularProbe == \basic).if({ ~probeMonitor[\oscFreq] = values.last; }, { ~subtractiveMonitor[\oscFreq] = values.last; });
        OSCdef(handler).notNil.if({ OSCdef(handler).func.value(["/monitor", ~regularDescriptors[~regularProbe][\synth].value.nodeID, 0] ++ values); });
    });
}, '/c_setn', s.addr);
~regularMonitorTask = Routine({ loop {
    var params, interval, count;
    interval = 0.25;
    ((~regularAudioStatus == "ready") and: { ~regularProbe.notNil } and: { ~regularMonitorBus.notNil }).if({
        params = ~regularDescriptors[~regularProbe][\params].value;
        (params[\monitorOn] >= 1).if({
            count = (~regularProbe == \basic).if({ 6 }, { 17 });
            s.sendMsg('/c_getn', ~regularMonitorBus.index, count);
            interval = 1 / params[\monitorRate].clip(0.1, 30);
        });
    });
    interval.wait;
}; }).play(AppClock);
OSCdef(\regularShutdown, { { ~regularBridgeCleanup.(); s.quit; AppClock.sched(0.5, { 0.exit; }); }.defer; }, '/regular/shutdown');
~regularHeartbeat = Routine({ loop {
    ((~regularAudioStatus == "ready") and: { s.serverRunning.not }).if({
        ~regularMute.(); ~regularAudioStatus = "failed";
        ~regularAudioError = "Audio server disconnected. Open Audio Setup to reconfigure / restart; no automatic fallback.";
    });
    ((Main.elapsedTime - ~regularLastContact) > 2).if({ ~regularMute.(); });
    ~regularMod.keys.do({ |effect| ~regularApplyFX.(effect); }); ~regularState.(); 0.25.wait;
}; }).play(AppClock);
~regularBridgeCleanup = {
    ~regularMute.(); ~regularGeneration = ~regularGeneration + 1;
    [~regularHeartbeat, ~regularMonitorTask, ~regularBootRoutine, ~regularSelectRoutine, ~regularOrderRoutine].do({ |routine| routine.notNil.if({ routine.stop; }); });
    ~activeProbeCleanup.notNil.if({ ~activeProbeCleanup.(); }); ~activeProbeCleanup = nil;
    ~basicProbeInstance = (~basicProbeInstance ? 0) + 1; ~subtractiveProbeInstance = (~subtractiveProbeInstance ? 0) + 1;
    ~regularFreeGraph.();
    [\regularRequest, \regularModulation, \regularPanic, \regularSamplePanic, \regularControlMonitor, \regularShutdown].do({ |key| OSCdef(key).free; });
    ~regularMonitorNotify = nil; ~regularUIOnly = false;
};
"Regular UI session ready for Audio Setup (audio server not started)".postln;
)

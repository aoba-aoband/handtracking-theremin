/* Evaluate this file in SC, or use Launch SC in main.py ui.
   Loopback-only control bridge; the existing probes own all DSP and mapping OSC.
   Requests are acknowledged and deduplicated. Scope windows show server signals. */
(
var root;
root = thisProcess.nowExecutingPath.standardizePath.dirname;
~regularBridgeCleanup.notNil.if({ ~regularBridgeCleanup.(); });
~regularSpecs = (root +/+ "regular_specs.scd").load;
~regularProbe = nil;
~regularInitializing = true;
~regularAddress = nil;
~regularSeen = Dictionary.new;
~regularBusy = nil;
~regularLastContact = Main.elapsedTime;
~regularSaved = ();
~regularDescriptors = (
    basic: (
        filename: "basic_receiver.scd", activeName: \basicReceiver,
        params: { ~probeParams }, synth: { ~basicReceiverSynth }, monitor: { ~probeMonitor },
        set: { |key, value| ~setProbeParam.(key, value); },
        release: { ~releaseBasicInput.(); },
        scope: { ~openProbeScope.(); }, spectrum: { ~openProbeFreqScope.(); }
    ),
    subtractive: (
        filename: "subtractive_probe.scd", activeName: \subtractiveProbe,
        params: { ~subtractiveParams }, synth: { ~subtractiveSynth }, monitor: { ~subtractiveMonitor },
        set: { |key, value|
            case
            { [\toneMinCutoff, \toneMaxCutoff].includes(key) } { ~setSubtractiveToneRange.(key, value); }
            { key == \toneInvert } { ~setSubtractiveToneInvert.(value); }
            { true } { ~setSubtractiveParam.(key, value); };
        },
        release: { ~releaseSubtractiveInput.(); },
        scope: { ~openSubtractiveScope.(); }, spectrum: { ~openSubtractiveFreqScope.(); }
    )
);
~regularState = {
    var pairs, params;
    (~regularAddress.notNil and: { ~regularProbe.notNil }).if({
        params = ~regularDescriptors[~regularProbe][\params].value;
        pairs = List.new;
        params.keysValuesDo({ |key, value| pairs.add(key.asString); pairs.add(value); });
        ~regularAddress.sendMsg(*(['/regular/state', ~regularProbe.asString] ++ pairs.asArray));
    });
};
~regularMonitorNotify = { |probe, monitor|
    var pairs;
    (~regularAddress.notNil and: { probe == ~regularProbe }).if({
        pairs = List.new;
        monitor.keysValuesDo({ |key, value| pairs.add(key.asString); pairs.add(value); });
        ~regularAddress.sendMsg(*(['/regular/monitor', probe.asString] ++ pairs.asArray));
    });
};
~regularMute = {
    var desc;
    ~regularProbe.notNil.if({
        desc = ~regularDescriptors[~regularProbe];
        desc[\set].value(\performanceGate, 0);
        desc[\release].value;
        desc[\synth].value.notNil.if({ desc[\synth].value.set(\uiMute, 1); });
    });
};
~regularAck = { |id|
    var parts;
    parts = id.split($:);
    ~regularSeen[parts[0]] = (~regularSeen[parts[0]] ? 0).max(parts[1].asInteger);
    ~regularBusy = nil;
    ~regularAddress.notNil.if({ ~regularAddress.sendMsg('/regular/ack', id); });
    ~regularState.();
};
~regularSet = { |probe, key, value|
    var spec, desc, quantized;
    spec = ~regularSpecs[probe][key];
    spec.notNil.if({
        quantized = value.asFloat.clip(spec[0], spec[1]);
        (spec[2] > 0).if({ quantized = quantized.round(spec[2]); });
        desc = ~regularDescriptors[probe];
        (probe == ~regularProbe).if({
            desc[\set].value(key, quantized);
        }, {
            ~regularSaved[probe].isNil.if({ ~regularSaved[probe] = (); });
            ~regularSaved[probe][key] = quantized;
        });
    });
};
~regularSelect = { |probe, done|
    var desc;
    (probe == ~regularProbe).if({ done.value; }, {
        ~regularMute.();
        ~regularProbe.notNil.if({
            ~regularSaved[~regularProbe] = ~regularDescriptors[~regularProbe][\params].value.copy;
        });
        ~regularProbe = nil;
        desc = ~regularDescriptors[probe];
        ~regularUIOnly = true;
        (root +/+ desc[\filename]).load;
        Routine({
            var count;
            count = 0;
            while { (~activeProbeName != desc[\activeName]) and: { count < 200 } } {
                0.1.wait; count = count + 1;
            };
            (~activeProbeName == desc[\activeName]).if({
                ~regularProbe = probe;
                ~regularSaved[probe].notNil.if({
                    ~regularSaved[probe].keysValuesDo({ |key, value|
                        ((key != \performanceGate) and: { ~regularSpecs[probe][key].notNil }).if({
                            ~regularSet.(probe, key, value);
                        });
                    });
                });
                ~regularMute.();
                ~regularUIOnly = false;
                done.value;
            }, { "Regular UI: probe boot failed; inspect the SC log".warn; ~regularBusy = nil; });
        }).play(AppClock);
    });
};
OSCdef(\regularRequest, { |msg, time, addr| {
    var id, operation, probe, key, value, parts;
    (addr.ip == "127.0.0.1").if({
        ~regularAddress = NetAddr(addr.ip, msg[1].asInteger);
        ~regularLastContact = Main.elapsedTime;
        id = msg[2].asString;
        parts = id.split($:);
        operation = msg[3].asString;
        ((~regularSeen[parts[0]] ? 0) >= parts[1].asInteger).if({
            ~regularAddress.sendMsg('/regular/ack', id);
        }, {
            ~regularBusy.isNil.if({
                ~regularBusy = id;
                case
                { operation == "select" } {
                    probe = msg[4].asSymbol;
                    (~regularInitializing == true).if({
                        ~regularBusy = nil; // Retry once the initial boot has finished.
                    }, {
                        ~regularDescriptors[probe].notNil.if({ ~regularSelect.(probe, { ~regularAck.(id); }); }, { ~regularAck.(id); });
                    });
                }
                { operation == "set" } {
                    probe = msg[4].asSymbol; key = msg[5].asSymbol; value = msg[6].asFloat;
                    ~regularSpecs[probe].notNil.if({
                        ~regularSet.(probe, key, value);
                        ((key == \performanceGate) and: { value >= 1 } and: { probe == ~regularProbe }).if({
                            ~regularDescriptors[probe][\synth].value.set(\uiMute, 0);
                        });
                    });
                    ~regularAck.(id);
                }
                { operation == "restore" } {
                    probe = msg[4].asSymbol;
                    ~regularMute.();
                    ~regularSpecs[probe].notNil.if({
                        msg.copyRange(5, msg.size - 1).clump(2).do({ |pair|
                            (pair[0].asSymbol != \performanceGate).if({ ~regularSet.(probe, pair[0].asSymbol, pair[1]); });
                        });
                    });
                    ~regularAck.(id);
                }
                { operation == "panic" } { ~regularMute.(); ~regularAck.(id); }
                { ["scope", "spectrum"].includesEqual(operation) } {
                    (~regularProbe.notNil).if({ ~regularDescriptors[~regularProbe][operation.asSymbol].value; });
                    ~regularAck.(id);
                }
                { true } { ~regularAck.(id); };
            });
        });
    });
}.defer; }, '/regular/request');
OSCdef(\regularPanic, { { ~regularMute.(); }.defer; }, '/regular/panic');
OSCdef(\regularShutdown, { {
    ~regularMute.();
    ~activeProbeCleanup.notNil.if({ ~activeProbeCleanup.(); });
    s.quit;
    AppClock.sched(0.5, { 0.exit; });
}.defer; }, '/regular/shutdown');
~regularHeartbeat = Routine({
    loop {
        ((Main.elapsedTime - ~regularLastContact) > 2).if({ ~regularMute.(); });
        ~regularState.();
        0.25.wait;
    };
}).play(AppClock);
~regularBridgeCleanup = {
    ~regularMute.();
    ~regularHeartbeat.stop;
    [\regularRequest, \regularPanic, \regularShutdown].do({ |key| OSCdef(key).free; });
    ~regularMonitorNotify = nil;
};
~regularSelect.(\basic, { ~regularInitializing = false; });
"Regular UI bridge listening on loopback OSC".postln;
)

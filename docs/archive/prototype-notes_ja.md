# 過去のプロトタイプ開発メモ

2026-10-21のドキュメント整理前の記録です。過去の挙動・実験・将来案が混在し、起動手順や実装状況は現在と異なる場合があります。現在の操作は[README](../../README_ja.md)と[クイックスタート](../../QUICKSTART_ja.md)を参照してください。

---

# Handtracking Theremin 日本語クイックガイド

Webカメラで手の動きを読み取り、音程・音量・音色を操作するテルミンのプロトタイプです。
現在はテルミンとしての演奏体験を中心に開発しています。将来ほかの楽器や音楽システムへ
広げられるよう、手の追跡・特徴量・音楽へのマッピング・出力は分離しています。

## 通常用UIの起動

以下は、このPCにある既存の作業フォルダから起動する例です。GitHubの名前変更後も
このフォルダ名はそのまま使えます。新規に取得した場合は `handtracking-theremin` フォルダで実行してください。

```powershell
cd C:\Users\aobaa\handtrack_music_platform
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe main.py ui
```

**Start** を押すと、必要に応じてSCを起動し、接続と設定の同期が終わってからカメラを開始します。
準備中は **Start pending** と表示されます。**Launch SC** でSCだけを先に起動することもできます。
F5：Start、F6：Stop、F12：PANIC。Camera／Controls／Analysis を切り離して移動・
サイズ変更・ドッキングでき、Patch と Layout はそれぞれ名前を付けて保存できます。
通常用UIは専用のOSCポート57121を使います。以下の従来の `hands` 起動手順も使えます。

詳しい操作、既存SCセッションへの接続、検証範囲と制約は
[Regular UI guide](../../gui/regular/README.md) を参照してください。

## このファイルの目的

このファイルは、プロトタイプを起動して音を出すための日本語ガイドです。

このプロジェクトは完成アプリではなく、練習・検証用プロトタイプです。UIもまだ仮のもので、Python側はOpenCV trackbar、SuperCollider側は簡易GUIを使っています。

## システム全体の概要

```text
Webカメラ
-> Python / OpenCV / MediaPipe
-> 手のランドマーク検出
-> pitch / scale / quantization / final_freq 生成
-> OSC送信
-> SuperCollider
-> Synth発音
```

Python側は手の検出、音程、スケール、量子化、OSC送信を担当します。

SuperCollider側は、Pythonから届いた `final_freq` を使って発音し、Lag、ポルタメント、ソフトクリッピング、フィルター、Performance Gateなどを担当します。

## V2a articulation decision（判断記録）

現在の判断:

- 左手 pinch には同時に2つの意味を持たせます。
  1. continuous amp control
  2. threshold + hysteresis による articulation gate の元信号

状態:

- 暫定で、いつでも戻せる設計です。
- これは V2a の sample mapping 実験であり、platform 全体の固定ルールではありません。

理由:

- 既存の連続的な音量表現を残せます。
- 新しい別ジェスチャーを要求せずに、発音開始と解放を試せます。
- 連続 pitch の楽器として、自然な実験にしやすい設計です。

今回は見送った代替案:

- pinch は amp だけを制御する。
- pinch は gate だけを制御する。
- 別のジェスチャーで articulation を制御する。
- Python は raw pinch だけを送り、SuperCollider 側で threshold gate を作る。

戻し方:

- `articulationOn = OFF` にすると V1.5 相当の聴こえ方に戻ります。
  continuous pinch amp は有効なまま、articulation envelope だけを bypass します。
- 新しい OSC address は `/sample/left/articulation/gate` として独立しています。
- 将来の mapping は、右手 pitch や左手 tone control を変えずに、この event を無視・置換・削除できます。

## 現在の到達点と再開方法（2026-10-19）

V1.5 の左手 tone control に続き、V2a の articulation / filter envelope と
V2a.1 の runtime calibration を実装しています。`articulationOn` と `filterEnvOn` は
初期値 OFF です。V2a を試すときは減算合成 probe の Controls で ON にします。

終了・通信断への対処も追加しました。

- Python は `q`、カメラエラー、Ctrl+C による終了時に `/sample/panic` を送信します。
- 両方の SC probe は panic で amp を 0 にします。減算合成では articulation gate も閉じます。
- 左手 pinch を一度受信した後、1秒間受信しなければ SC 側でも同じ消音処理を行います。
  監視は0.1秒間隔で、実際の音量低下には設定済みの amp release と FX の余韻が加わります。
- 手の検出喪失で gate が閉じた後も、Python は OFF を繰り返し送り、UDP 欠落に備えます。
- 左手 pinch の受信が再開すると音量操作も復帰します。手動 Performance Gate は保持します。

単体の `gui/theremin_gui.py` も現行の MediaPipe Tasks API に移行しました。
これは sounddevice で直接発音する別ランチャーで、SC 用の Mapping Settings とは別です。

自動確認:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
& 'C:\Program Files\SuperCollider-3.14.1\sclang.exe' -D (Join-Path $PWD 'tests\sc_input_lifecycle.scd')
```

Python テスト、付属モデルの初期化、SC 全体のコンパイル、SynthDef の生成、
受信タイムアウト・復帰・panic の自動検証まで確認済みです。
次は下記の通常起動コマンドでカメラと SC を起動し、演奏しながら閾値を校正してください。
発音中の `q`、カメラ切断、Python の強制停止、probe の切り替え時の消音・後始末、
手の再検出時の復帰と聴感は実機確認が残っています。低遅延モードと Ableton 連携は未実装です。

## 初回セットアップ

Windows PowerShell想定:

```powershell
git clone https://github.com/aoba-aoband/handtracking-theremin.git
cd handtracking-theremin
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

PowerShellでvenv有効化が止まる場合:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## SuperCollider側の起動

1. SuperColliderを起動します。
2. 既存の加算合成 / FX probe を使う場合は `sc/basic_receiver.scd`、独立した
   減算合成 probe を使う場合は `sc/subtractive_probe.scd` を開きます。
3. 選んだファイル全体、または外側のブロックを評価します。
4. Post windowに以下のような表示が出ればOKです。

```text
creating probe synth
Listening for generic hand control events on port 57120
Listening for sample mapping events that control the probe synth.
```

SC側は `127.0.0.1:57120` でOSCを待ち受けます。

評価すると `Probe Synth Controls` window が出ます。初期状態では Performance Gate がOFFなので、音が出ない場合は Gate button または spacebar を押してください。

## Python側の起動

通常起動:

```powershell
python main.py hands --sample-mapping --send-osc --show-pitch-guides --show-settings-panel
```

量子化ON:

```powershell
python main.py hands --sample-mapping --send-osc --show-pitch-guides --show-settings-panel --quantize-pitch
```

現在の処理時間を測りたい場合:

```powershell
python main.py hands --sample-mapping --send-osc --show-pitch-guides --show-settings-panel --show-performance-stats
```

`--show-performance-stats` は、低遅延化そのものではなく、どこで時間がかかっているかを測るための表示です。
capture、MediaPipe推論、features生成、mapping、OSC送信、描画、display/wait、total frame time、実効FPSを
1秒ごとにコンソールへまとめて表示します。OSCアドレスや手の認識、描画、送信頻度は変更しません。

起動すると、カメラpreviewと `Pitch Settings` window が開きます。

- `q` で終了します。
- `--send-osc` がないとSCに値が送られません。
- `--sample-mapping` がないと右手pitch / 左手pinchのサンプル音楽マッピングが出ません。

## 基本操作

- 右手上下でpitch candidateを操作します。
- 右手の中指を人差し指より上にすると1オクターブ上がります。
- 左手pinchでamp candidateを操作します。
- SuperCollider側のGateがOFFだと音は出ません。
- SC側Gate buttonまたはspacebarで音を立ち上げ/立ち下げします。
- Python preview windowで `q` を押すと終了します。

## Python側UI: Pitch Settings

- Pitch Min note
- Pitch Max note
- Root
- Scale
- Quantize
- Guide Mode

## SuperCollider側UI: Probe Synth Controls

Performance / Gate:

- Gate button / spacebar
- crescendoTime
- decrescendoTime

Lag / Portamento:

- freqLag
- ampLag
- portamento
- portamentoTime

Soft clipping:

- softClip
- softClipDrive
- softClipMix

Filter:

- filter
- filterCutoff
- filterRq
- filterMix
- filterLag

Output / amp range:

- outputLevel
- ampMin
- ampMax
- Reset defaults

## SuperCollider側の音作りモニター

`sc/basic_receiver.scd` を評価すると、従来の `Probe Synth Controls` に加えて
`Probe Synth Monitor` が開きます。これは完成UIではなく、probe synth の
音作りを確認するための小さなモニターです。

- `targetFreq` / `followedFreq` で、Pythonから届いた周波数とSynth内部で追従中の周波数を確認できます。
- `targetAmp` / `followedAmp` で、左手pinchから作られたampとSynth内部のampを確認できます。
- Gate状態、`performanceEnv`、`outputLevel`、softClip、filter、`filterFreq` を確認できます。
- `Open Scope` で最終出力の波形を見られます。
- `Open FreqScope` で、softClipやfilter調整時の倍音・高域の変化を見られます。

softClipやfilterを調整するときの目安として使ってください。Python側のOSCアドレスや起動コマンドは変わりません。

`Probe Synth Visualizer` には、音作り用の概念図も表示されます。

- LPFの図で、どの周波数から高域を削っているかを見られます。
- filterCutoff、filterRq、filterMix の変化が、ざっくりしたフィルター形状として反映されます。
- softClipの図で、driveによる波形の潰れ方とmixによるdryへの戻り方を見られます。
- pitch followの図で、`targetFreq` と `followedFreq` のズレや追従の遅れを見られます。

これらは正確な測定器ではなく、probe synth の音作りを直感的に進めるための目安です。
LPF / Filter 図は、単純な概念カーブではなく RLPF に近い近似カーブにしています。
縦軸は dB 表示で、`+12 dB` から `-36 dB` の範囲、`0 dB` 基準線、dB目盛りにより、
cutoff付近のピークと高域の減衰を見やすくしています。
ただし実測器ではなく、音作り用の近似表示です。`filterRq` は小さいほど
cutoff付近が鋭く/共鳴っぽくなりやすいので、素直に高域を丸めたい場合は
`filterRq` を `0.5`〜`1.0` くらいにすると扱いやすいです。

今回の拡張で、`Probe Synth Additive / FX Controls` も追加されています。

- オルガン型の加算合成を追加しました。
- 12倍音を個別に調整できます。
- 加算合成音は base sine と混ぜてから softClip / filter に入ります。
- main filter の後にフィルター付きディレイを追加しました。
- delay の後にリバーブを追加しました。
- Visualizer の LPF 図には、周波数目盛りも表示されます。

どれも完成仕様ではなく、probe synth の音作り用の拡張です。

## SuperCollider側UI: Subtractive Probe Controls（V1）

`sc/subtractive_probe.scd` は、既存の `basic_receiver.scd` へ追加するものでは
ない、独立した減算合成用 probe です。`basic_receiver.scd` は加算合成、soft clip、
delay、reverb も含む広い音作り用 probe としてそのまま使えます。こちらは
`音源 -> filter -> amp -> output` を学びながら試せる、教育的かつ演奏可能な V1 です。

SuperCollider で `sc/subtractive_probe.scd` を評価した後、Python は従来どおり
次のコマンドで起動します。

```powershell
python main.py hands --sample-mapping --send-osc --show-pitch-guides --show-settings-panel
```

使う OSC は既存の2つだけです。

- `/sample/right/pitch/final_freq` -> subtractive synth の `freq`
- `/sample/left/pinch` -> `ampMin..ampMax` に変換して subtractive synth の `amp`

信号経路:

```text
oscillators / sub / noise
-> source mix
-> RLPF
-> amp response
-> performance gate
-> LeakDC / Limiter
-> Out
```

Controls は以下です。

- Performance / Response: Gate、`crescendoTime`、`decrescendoTime`、`freqLag`、
  `ampAttack`、`ampRelease`、`outputLevel`、`ampMin`、`ampMax`
- Oscillators: Saw / Pulse / Triangle を選べる oscillator 1、ON/OFFできる
  oscillator 2、octave、detune、`oscMix`、手動 `pulseWidth`、`subMix`、`noiseMix`
- Filter: `filterOn`、指数スケールの `filterCutoff`、`filterRq`、`filterMix`、
  `filterLag`、`keyTracking`

`keyTracking = 0` では cutoff は基本的に固定です。値を上げると高い pitch に応じて
実効 cutoff も上がるため、高音でも相対的な明るさを保ちやすくなります。

Gate button と、`Subtractive Probe Controls` window にフォーカスがあるときの
spacebar は同じ performanceGate を切り替えます。`Reset defaults` は GUI と実行中
Synth を同じ初期値へ戻します。別ウィンドウの monitor では target/followed
freq・amp、gate envelope、実効 cutoff、filter 状態、oscillator 波形、outputLevelを
表示し、`Open Scope` / `Open FreqScope` で最終出力を確認できます。

`basic_receiver.scd` と `subtractive_probe.scd` は同時使用ではなく、どちらか片方を
評価して切り替えてください。両ファイルは小さな共通 cleanup を持つため、片方を評価
するともう片方の Synth、sample-mapping OSCdef、control / monitor window を停止・
閉じます。同じファイルの再評価でも古い Synth、OSCdef、window を置き換えます。

V1では LFO、PWM、filter envelope、ADSR、note-on / note-off、pinch threshold gate、
unison、HPF / BPF、delay、reverb、custom visualizer、新しい Python gesture / OSC
address は実装していませんでした。下の V2a では、このうち sample mapping 実験として
articulation gate と filter envelope だけを独立して追加しています。

## V1.5: 左手横位置による Tone Control

V1.5 では既存の Python 起動コマンドを変えずに、左手 index tip X 由来の
`/sample/left/tone/norm`（`0..1`）を追加しました。

```powershell
python main.py hands --sample-mapping --send-osc --show-pitch-guides --show-settings-panel
```

Python 側は X 方向を反転せず、Hz への変換や smoothing もせず、neutral-ish な tone
candidate を送るだけです。`sc/subtractive_probe.scd` がこれを RLPF cutoff として
解釈します。`sc/basic_receiver.scd` はこの新しい OSC を使用しません。

`handToneOn` が OFF のときは、V1 と同じ手動 `Manual cutoff`（`filterCutoff`）を
使います。ON のときは `toneInvert` で方向を必要に応じて反転し、
`toneMinCutoff..toneMaxCutoff` の指数スケールへ変換した `handToneCutoff` を
base cutoff として使います。その後に `keyTracking`、両方の cutoff に共通の
`filterLag` が適用されて RLPF へ入ります。

`toneMinCutoff` / `toneMaxCutoff` は暗さ〜明るさの演奏レンジで、UI は min/max の
逆転を防ぎます。`toneInvert` は左手の左右方向と bright/dark の対応を反転します。
Subtractive Probe Monitor では mode、target tone norm、mapped hand tone cutoff、
manual cutoff、effective cutoff を確認できます。

## V2a: Articulation Gate + Filter Envelope

V2a では sample mapping の OSC event を1つ追加します。

```text
/sample/left/articulation/gate
```

Python 側は左手 pinch から threshold + hysteresis でこの gate を作ります。
デフォルトは `articulation_gate_on_threshold = 0.65`、
`articulation_gate_off_threshold = 0.45`、
`articulation_hand_loss_release_seconds = 0.25` です。左手が一時的に見えなくなっても
すぐには gate を閉じず、timeout を超えたら `0` を送ります。Python 側は envelope の
時間形状、ADSR、cutoff への変換は担当しません。`/sample/left/pinch`、
`/sample/left/tone/norm`、`/sample/right/pitch/final_freq` は従来どおり送ります。

### V2a.1: Runtime Mapping Calibration

`--show-settings-panel` を付けると、既存の `Pitch Settings` に加えて、OpenCV の
`Mapping Settings` window が開きます。演奏中に次の項目を調整できます。

- Articulation threshold
- Hysteresis width
- Hand-loss release time（ms）

校正値の関係は次のとおりです。

```text
gateOn  = threshold
gateOff = max(0, threshold - hysteresis width)
```

pinch が `gateOn` 以上なら gate が開き、`gateOff` 以下なら閉じ、その間では直前の
gate 状態を維持します。camera preview の `Articulation Mapping` 表示では、現在の
左手 raw pinch、gate の ON/OFF、実効 on/off threshold、hand-loss release time を
確認できます。

pinch 値は camera 距離、手の大きさ、手の開き方に影響されます。固定の初期値を唯一の
正解とは考えず、自然な演奏距離で live monitor を見ながら校正してください。GUI の
変更は即時反映されますが、現在の session 中だけ有効です。`config.py` は次回起動時の
初期値として使われ、GUI から書き換えられません。

将来は articulation source を `left pinch`、`right pinch`、
`left hand proximity candidate`、`right hand proximity candidate`、`off` から選べる
Mapping GUI を検討しています。ただし proximity candidate は、単眼 Web camera で
物理的距離を測定するという意味ではなく、演奏用特徴量として別途検証する候補です。
V2a.1 は左手 pinch 固定のままで、stereo vision や depth camera 依存を追加しません。

SuperCollider 側は `/sample/left/articulation/gate` を受け取り、以下を担当します。

- articulation amp envelope
- filter envelope
- envelope timing と cutoff 倍率

`articulationOn` の初期値は OFF です。OFF のときは V1.5 と同じ continuous pinch amp の
挙動に戻り、gate event が届いても音量が強制的に切れません。ON のときは
`articulationGate` が `articulationAttack` で開き、`articulationRelease` で解放されます。
これは `ampAttack` / `ampRelease` とは別の役割です。

- `ampAttack` / `ampRelease`: continuous pinch amp の追従時間
- `articulationAttack` / `articulationRelease`: gate で作る発音・解放の形

`filterEnvOn` の初期値も OFF です。OFF のときは base cutoff への filter envelope 倍率は
かかりません。filter envelope は `filterEnvOn` と `articulationOn` が両方 ON のときだけ
有効です。`filterEnvAmountOctaves` は Hz 加算ではなく octave 単位の倍率で、値を大きく
するほど発音開始時に cutoff が大きく開きます。

V2a の信号経路:

```text
oscillators / sub / noise
-> source mix
-> RLPF
-> followed pinch amp
-> articulation amp envelope
-> performance gate
-> LeakDC / Limiter
-> Out
```

filter 側の経路:

```text
manual cutoff or hand-tone cutoff
-> key tracking
-> filter lag
-> optional filter envelope
-> RLPF cutoff
```

まだ実装していない候補:

- LFO
- PWM
- pinch 以外の articulation gesture
- explicit trigger event
- alternate filter types
- unison
- polyphony

## よくあるトラブル

音が出ない:

- SuperColliderで `sc/basic_receiver.scd` を評価したか確認します。
- `Probe Synth Controls` のGateがONか確認します。
- Python起動コマンドに `--send-osc` があるか確認します。
- 左手pinchや `ampMin` / `ampMax`、`outputLevel` を確認します。

カメラは出るが音が変わらない:

- Python起動コマンドに `--sample-mapping` があるか確認します。
- SuperColliderのPost windowにOSC受信メッセージが出ているか確認します。
- 右手/左手のhandednessが想定と逆になっていないか確認します。

Quantizeしているのにガイドと音が合わない:

- Python側のPitch SettingsでRoot / Scaleを確認します。
- Guide Modeがscaleになっているか確認します。
- guide設定とquantize設定が同じ値になっているか確認します。

SC側でスペースバーが効かない:

- `Probe Synth Controls` windowにフォーカスがあるか確認します。
- Gate buttonでも同じ操作ができます。

## 現在の制限

- OpenCV trackbar UIは仮です。
- Root / Scaleは数値UIで直感的ではありません。
- hand index / handednessはまだ完全な安定ロール追跡ではありません。
- tracking dropoutで音が跳ぶことがあります。
- SC音色はまだprobe synthです。
- Ableton / Max for Live連携は今後の課題です。

## 確認ポイント

- `sc/basic_receiver.scd` を評価してエラーがない。
- `Probe Synth Controls` windowにfilter系UIが出る。
- filterをONにすると音色が丸くなる。
- filterCutoffを下げると高域が削れる。
- filterRqを変えるとcutoff付近の癖が変わる。
- filterMixでdry/filterの混ざり方が変わる。
- softClip + filterの組み合わせで、歪ませた音を丸められる。

## 低遅延化の前に測る

`--show-performance-stats` で、現在の camera capture / MediaPipe / mapping / OSC / drawing / display の
処理時間を確認できます。表示間隔は `--performance-stats-interval 2.0` のように変更できます。

`--show-performance-stats` の出力は `logs/` に保存し、`tools/plot_perf_log.py` でCSVとPNGグラフに変換できます。
平均処理時間だけでなく、折れ線グラフで時間変化も見られるので、低遅延化前後の比較に使えます。

performance logを保存する例:

```powershell
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
python main.py hands --sample-mapping --send-osc --show-pitch-guides --show-settings-panel --show-performance-stats *>&1 | Tee-Object -FilePath "logs\perf_$ts.txt"
```

特定のログをCSVとグラフに変換する例:

```powershell
python .\tools\plot_perf_log.py .\logs\perf_YYYYMMDD_HHMMSS.txt --out-dir .\analysis\perf_YYYYMMDD_HHMMSS
```

生成されるファイル:

- `perf_summary.csv`
- `total_frame_time.png`
- `fps_over_time.png`
- `stage_timings_over_time.png`
- `average_stage_breakdown.png`
- `max_stage_breakdown.png`
- `hands_vs_mediapipe.png`

おすすめの見る順番:

- `average_stage_breakdown.png`
- `stage_timings_over_time.png`
- `total_frame_time.png`
- `fps_over_time.png`
- `hands_vs_mediapipe.png`

`logs/` と `analysis/` は生成物用ディレクトリで、Gitのignore対象です。
performance log、CSV、PNGグラフはGitに入れないでください。

これは計測だけの機能で、`--low-latency` はまだ未実装です。Capture thread、最新フレーム1枚方式、
OpenCV描画停止、OSC送信間引きなどの挙動変更は、次の別作業として分けるのがよさそうです。

```text
次は Python側の --low-latency を追加してください。
sc/basic_receiver.scd は変更しないでください。
```

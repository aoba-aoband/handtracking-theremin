# Handtracking Theremin

[English](README.md) · [クイックスタート](QUICKSTART_ja.md) · [Quick Start](QUICKSTART.md) · [ユーザーマニュアル](USER_MANUAL_ja.md)

Webカメラで手の動きを読み取り、音程・音量・音色を操作するテルミンのプロトタイプです。
Python / MediaPipeで手を検出し、音楽用の制御イベントをOSCでSuperColliderへ送り、発音します。
現在はテルミンとしての演奏体験を中心に開発しています。手の追跡・特徴量・マッピング・出力は、
将来ほかの楽器へ展開できるよう分離しています。

## はじめに

演奏する方は[ユーザーマニュアル](USER_MANUAL_ja.md)をご覧ください。起動・演奏・音色作り・保存・困ったときの操作を、画面のボタン名に沿って説明しています。

初回セットアップ・最初の発音・トラブル対処は[クイックスタート](QUICKSTART_ja.md)を参照してください。
依存関係を導入済みの環境では、リポジトリ直下でPowerShellから起動します。

```powershell
.\venv\Scripts\python.exe main.py ui
```

**Start** または **F5** を押すと、必要に応じてSCを起動します。接続と設定同期が終わるまで
**Start pending** と表示し、その後カメラを開始して最初のフレームを受信してからGateを開きます。
**Launch SC** は、カメラを開始せずSCだけを先に起動する操作です。

これまでの検証環境はWindows、Python 3.10.8、SuperCollider 3.14.1です。
MediaPipeモデルは `models/hand_landmarker.task` に同梱しています。
現在のUIとSCの自動検出はWindowsを対象とし、ほかのOSでは未検証です。

## 起動経路

| 起動方法 | 用途 | 発音・OSC |
| --- | --- | --- |
| `main.py ui` | 通常用UI：Camera / Controls / Analysis | SC bridge。既定は `127.0.0.1:57121` |
| `main.py hands` | OpenCVのランドマーク表示・マッピング確認 | `--send-osc` 指定時に送信。宛先は `config.py`、既定は `57120` |
| `main.py camera` | カメラ映像だけの確認 | なし |
| `main.py` または `main.py osc` | OSC疎通テスト | `config.py` の宛先へ汎用テストイベントを送信 |
| `gui/theremin_gui.py` | 別系統のTkinter / sounddevice版 | ローカルで直接発音。SC probeや通常用UIのPatchとは独立 |

CLIの引数一覧は `main.py --help` で確認できます。`hands` からSC probeを演奏するには
`--sample-mapping` が必要です。汎用の `/hand/...` イベントだけでは発音を制御しません。

## 通常用UI

Camera・Controls・Analysisは独立してドッキング・フローティングできるパネルです。
タイトルのダブルクリックまたはFloatボタンで切り離し、移動・サイズ変更・別モニターへの配置ができます。
タイトルをドラッグして再ドッキングできます。作業画面をタブに隠す構成にはしていません。
Cameraの **Settings** で、長いマッピング・音程設定の表示を切り替えます。

| 操作 | キー | 動作 |
| --- | --- | --- |
| Start | F5 | SCの準備を待ち、カメラを開始してGateを開く。PANIC後の再開にも使用 |
| Stop | F6 | 開始待機をキャンセルし、消音してカメラを停止 |
| PANIC | F12 | 即時消音してGateを閉じる。動作中のカメラは継続 |

フローティング中も各パネルのボタンとショートカットを使えます。通常用UIではSpaceを演奏操作に使いません。
PatchのRecall・Reset Defaults・再接続・probe切り替えではGateを閉じたままにします。
演奏を再開するにはStartを押してください。

### 両手の操作と音程

| 入力 | 現在のsample mapping |
| --- | --- |
| 右手の人差し指の高さ | Min / Maxの範囲内で指数的に音程を変換 |
| 右手の中指先が人差し指先より上 | 量子化の前に1オクターブ上げる |
| 左手の親指と人差し指の距離（`pinch`） | 連続的な音量操作 |
| 左手の人差し指の横位置 | Subtractive ProbeでHand Toneを有効にした場合の入力 |
| 左手pinchの閾値・ヒステリシス | Subtractive Probeで有効にした場合のarticulation gate |

`pinch` は画像座標上の正規化距離で、親指と人差し指を離すほど値が増えます。
「つまむ強さ」の逆数や実際の物理距離ではありません。CameraのLeft / Right検出表示も確認してください。

Rootは12音すべて、Scaleはソース順で `chromatic`、`major`、`minor`、`major-pentatonic`、
`minor-pentatonic` です。Guide Modeは `simple` / `chromatic` / `scale`、QuantizeはOFF / ONです。
Min / Maxはそれぞれ音名（MIDI 0〜127）またはHzで設定でき、Root / Scaleに制限されません。
Min < Maxが必要です。オクターブ操作後の最終音程は、この基準音域の上限を超える場合があります。

起動時の初期値はMin 220 Hz、Max 880 Hz、Root A、Scale `minor-pentatonic`、
Quantize OFF、Guide Mode `simple` です。pinch gateの初期値はON閾値0.65、OFF閾値0.45、
検出喪失から解放まで0.25秒です。通常用UIのマッピング設定はPatchに保存できます。
手の高さから音域を校正する機能はありません。

### ProbeとAnalysis

Controls上部の **Probe** は、音源と処理経路全体を切り替えます。
両probeの設定はセッション内とPatchに個別に保持します。

| Probe | 使用できる処理 |
| --- | --- |
| Basic / Additive | 基本のsine、12倍音、追従、portamento、soft clip、filter、delay、reverb |
| Subtractive | Osc 1 / Osc 2（Saw / Pulse / Triangle）、sub / noise、filter、key tracking、Hand Tone、articulation、filter envelope |

現行ソース由来のカタログは、読み取り専用項目を含めてBasic 46項目・Subtractive 41項目です。
正式なSCパラメーター名はツールチップで確認できます。ArticulationとFilter Envは初期値OFFで、
filter envelopeを有効にするには両方をONにします。

AnalysisはSCから受信した `followedFreq`・`effectiveCutoff` などを使います。
Filter・Envelopeの図は計算モデルであることを表示しています。**Open Scope** と
**Open FreqScope** は、実際の信号を見るSCのネイティブウィンドウを開きます。
未接続・受信期限切れの値を測定値として補完しません。
パラメーター仕様と接続の詳細は[Regular UI guide](gui/regular/README.md)を参照してください。

### PatchとLayout

- **Patch**：名前を入力してSaveし、一覧から選んでRecallします。両probe・音程・マッピングを復元します。
  RecallではGateを閉じたままにします。
- **Layout**：パネルの位置・サイズ・ドッキング・Camera Settingsの表示を別に保存します。
  最後のレイアウトは次回起動時にも復元します。
- 保存先は `user_data/patches/`、`user_data/layouts/`、`user_data/session-layout.json` です。
  いずれもGitの追跡対象外です。
- パラメーターの変更は再起動時に自動復元しません。残したい設定はPatchに保存し、Recallしてください。
  LayoutのRecallでは音色設定を変更しません。

## SC接続と診断

通常用UIは専用の `sclang` を言語ポート **57121** で起動し、`scsynth` の音声サーバー用ポートは
別に自動確保します。`config.py` の送信先は従来のCLI用で、通常用UIのポート設定ではありません。
既存のSCセッションへ接続する場合は[sc/regular_bridge.scd](sc/regular_bridge.scd)を評価してから、
その言語ポート（通常は `57120`）を指定します。

```powershell
.\venv\Scripts\python.exe main.py ui --ui-sc-port 57120
```

UI終了時に終了させるのは、UI自身が起動したSCプロセスだけです。
外部のSCセッションにはPANICを送り、セッション自体は閉じません。1つの受信先に対する演奏送信元は1つにしてください。

通常用UIとの通信が約2秒途絶えるとbridgeが消音します。両probeには、左手pinchを一度受信した後、
1秒間受信しなければ入力を解放する監視もあります。確認間隔は0.1秒です。
入力の解放には通常のrelease時間やFXの余韻が加わる場合がありますが、通常用UIのPANICは出力を即時ミュートします。

カメラエラー・SCの起動タイムアウト・無音の場合は[クイックスタートの対処手順](QUICKSTART_ja.md#困ったとき)を参照してください。
既定のSCログは `logs/regular-sc.log`、別ポート指定時は `logs/regular-sc-<port>.log` です。

## 開発と検証

```text
Camera → src/hand_tracker.py → src/features.py → src/mapping.py / src/pitch.py
       → OSC → sc/regular_bridge.scd → selected SC probe → audio output
```

音域・オクターブ・スケール・量子化はPython、音源・追従・音量整形・FXはSCが担当します。
`/hand/0` と `/hand/1` は検出順であり、固定の個体IDではありません。
`/sample/right/...`・`/sample/left/...` はhandednessを短期間の揺れに対して安定化して使いますが、
完全な個体追跡ではありません。

| 場所 | 役割 |
| --- | --- |
| `main.py`、`config.py` | 起動経路、CLI・マッピングの初期値 |
| `gui/regular/` | Qtパネル、設定保存、SC通信、カメラワーカー |
| `src/` | 追跡・特徴量・マッピング・音程・OSC出力 |
| `sc/basic_receiver.scd`、`sc/subtractive_probe.scd` | probeのパラメーター・DSP・受信・後始末 |
| `tools/`、`tests/` | カタログ生成、検証、処理時間の分析 |

自動テストはリポジトリ直下で実行します。

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
& 'C:\Program Files\SuperCollider-3.14.1\sclang.exe' -D (Join-Path $PWD 'tests\sc_input_lifecycle.scd')
```

SCの実行ファイルのパスは導入環境に合わせて変更してください。
SC lifecycleテストはカメラ・音声サーバー不要です。実際のSC / OSC接続を別ポート57122で確認するには、次を使います。

```powershell
.\venv\Scripts\python.exe tools\verify_regular_connection.py
.\venv\Scripts\python.exe tools\verify_regular_connection.py --camera
```

専用の音量0のSCサーバーを起動し、終了時に閉じます。`--camera` は本番のStart / Stopと映像の受け渡しも確認します。
カメラを使うほかのアプリは先に停止してください。`--scopes` を追加するとSCの信号表示ウィンドウを開きます。
これらの自動検証とは別に、聴感・演奏の確認が必要です。

SCパラメーター仕様を変更したら、検証テーブルを再生成してテストしてください。

```powershell
.\venv\Scripts\python.exe tools\generate_regular_specs.py
```

従来のCLI診断と処理時間のログ・グラフ化は[クイックスタートのCLI診断](QUICKSTART_ja.md#cliで個別に確認する)を参照してください。
`logs/`、`analysis/`、`user_data/` は生成物・ローカルデータ用でGitの追跡対象外です。

## 制限と開発記録

検出喪失やhandedness・検出順の変化で値が跳ぶ場合があります。聴感・長時間の演奏、
ネイティブScopeの表示内容、実際の別モニターへの配置は手動検証の対象です。
実機での挙動はカメラとSCの音声デバイスにも依存します。
Ableton / Max for Live連携、専用の低遅延モード、LFO、PWM、unison、polyphonyは未実装です。

V2aの判断記録や将来案を含む以前の記述は[過去のプロトタイプ開発メモ](docs/archive/prototype-notes_ja.md)へ保存しました。
履歴資料として参照し、現在の起動・操作にはこのREADMEとクイックスタートを使ってください。

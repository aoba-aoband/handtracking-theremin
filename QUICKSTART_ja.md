# Handtracking Theremin — クイックスタート

[English](QUICKSTART.md) · [プロジェクトREADME](README_ja.md) · [ユーザーマニュアル](USER_MANUAL_ja.md)

演奏の操作を順に知りたい方は[ユーザーマニュアル](USER_MANUAL_ja.md)をご覧ください。このクイックスタートには、セットアップ担当者向けの情報も含みます。

Windows PowerShellで、MediaPipe・OSC・SuperColliderを使う通常用UIを起動する手順です。
別系統のsounddevice版ランチャーは、この起動経路に含みません。

## 1. 初回セットアップ

Python、Git、SuperCollider、Webカメラ、音声出力が必要です。
これまでの検証環境はWindows、Python 3.10.8、SuperCollider 3.14.1です。
UIを起動する前にSuperColliderを導入してください。
自動検出は `C:\Program Files\SuperCollider*\sclang.exe` を探します。ほかの場所への導入は後述の方法で接続します。

新規取得の場合：

```powershell
git clone https://github.com/aoba-aoband/handtracking-theremin.git
cd handtracking-theremin
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

MediaPipeモデルは `models/hand_landmarker.task` に同梱しています。
仮想環境のPythonを直接呼ぶため、venvの有効化やPowerShellの実行ポリシー変更は不要です。

取得済みなら既存フォルダを使い、cloneは省略してください。古いローカルフォルダ名が
`handtrack_music_platform` でも起動できます。GitHubの名前変更に合わせたフォルダ名の変更は不要です。
依存関係が変更された更新後は、requirementsのインストールを再実行してください。

## 2. 起動して演奏する

リポジトリ直下で実行します。

```powershell
.\venv\Scripts\python.exe main.py ui
```

1. **Start** または **F5** を押します。SCのIDEを別途起動する必要はありません。
2. **Start pending** の間は、SCの起動・接続・設定同期を待ちます。
3. **SC connected**・**Camera running** と、映像・ランドマークの表示を確認します。
4. 両手をカメラに映します。右手の人差し指を上下すると音程、左手の親指と人差し指を
   離す・近づけると音量が変わります。Left / Rightの検出表示も確認してください。
   右手の中指先を人差し指先より上にすると1オクターブ上がります。
5. **Stop / F6** で消音してカメラを停止します。**PANIC / F12** は即時消音し、動作中の
   カメラは継続します。**Start / F5** で再開します。

初期音域はオクターブ操作前で220〜880 Hz、Root A、Scale `minor-pentatonic`、Quantize OFFです。
変更する場合はCameraの **Settings** を開きます。Controls上部でBasic / Additiveまたは
Subtractiveを選ぶと、probe全体が切り替わります。切り替え・PatchのRecall後はStartで再開してください。

## 3. 設定と配置を保存する

- **Patch** の名前を入力して、その横の **Save** を押します。一覧から選んで **Recall** すると、
  両probe・音程・マッピングを復元します。RecallではGateを閉じたままにします。
- Camera・Controls・Analysisのタイトルをダブルクリックすると切り離せます。
  タイトルをドラッグして再ドッキングできます。**Layout** の名前を付けて **Save** すると、
  配置を音色とは別に保存します。最後の配置は次回起動時にも復元します。
- パラメーターの変更は再起動時に自動復元しません。残したい設定はPatchへ保存してください。
  保存先はローカルの `user_data/` です。

## 困ったとき

| 症状 | 確認すること |
| --- | --- |
| UIが開かない／`PySide6` などが見つからない | 起動に使う `venv` のPythonでrequirementsをインストールし直します。コンソールのエラーも確認してください。 |
| Start pendingのまま進まない | ステータスと `logs/regular-sc.log` を確認します。45秒で開始待機を解除します。SCの導入先や音声デバイスのエラーを確認してください。 |
| SC connectedだが映像が出ない | SCへの接続だけではカメラは開始しません。Startを押し、映像の上に残る **Camera error** を確認します。他アプリのカメラ使用を止めて再試行するか、下記の方法でカメラ番号を変えます。 |
| 映像は出るが無音 | GateがONか、Output Level・Amp Min / Max・手の検出・SCログ・システムの音声出力を確認します。PANIC・Recall・probe切り替え後はStartを押します。 |
| Filter / Envelopeの図は動くがScopeが使えない | 図は計算モデルです。ScopeにはSC音声サーバーへの接続が必要で、現在のSC値の受信にはMonitorをONにします。 |
| 左右の操作や音程が合わない | Left / Rightの検出表示、オクターブ操作、Camera SettingsのRoot / Scale / Quantize・Min / Maxを確認します。Guide Modeの変更だけでは量子化しません。 |

カメラ番号を変える場合は、現在のUIを停止・終了してから起動します。

```powershell
.\venv\Scripts\python.exe main.py ui --camera-index 1
```

SCを自動検出対象外の場所へ導入した場合は、SCのIDEで `sc/regular_bridge.scd` の外側のブロックを評価します。
そのセッションの言語ポート（通常は57120）を指定し、Startを押します。

```powershell
.\venv\Scripts\python.exe main.py ui --ui-sc-port 57120
```

通常用UIの既定は57121、従来のCLIは `config.py` の設定（既定57120）です。
UI終了時はUI自身が起動したSCを閉じます。外部から開いたSCは終了させません。

## CLIで個別に確認する

カメラを使う処理は1つずつ実行してください。通常用UIのカメラは先にStopします。
OpenCVのプレビューでは、そのウィンドウにフォーカスして `q` で終了します。

```powershell
.\venv\Scripts\python.exe main.py camera
.\venv\Scripts\python.exe main.py hands --show-features
```

従来の音楽用OSC経路は、SCのIDEで `sc/basic_receiver.scd` または `sc/subtractive_probe.scd`
の片方を先に評価してから実行します。

```powershell
.\venv\Scripts\python.exe main.py hands --sample-mapping --send-osc --show-pitch-guides --show-settings-panel
```

SCのprobe操作ウィンドウでGateをONにします。そのウィンドウにフォーカスしている場合はSpaceでも切り替えられます。
通常用UIのF5 / F6 / F12とは別の操作です。`--quantize-pitch` を追加すると量子化できます。
引数一覧は `.\venv\Scripts\python.exe main.py --help` で確認してください。

CLIの処理時間を記録・グラフ化する例です。SC側は先に起動しておきます。

```powershell
New-Item -ItemType Directory -Force logs | Out-Null
.\venv\Scripts\python.exe main.py hands --sample-mapping --send-osc --show-pitch-guides --show-settings-panel --show-performance-stats *>&1 | Tee-Object -FilePath logs\perf.txt
.\venv\Scripts\python.exe tools\plot_perf_log.py logs\perf.txt --out-dir analysis\perf
```

集計CSVと処理時間・FPSのPNGを出力します。これは計測機能で、低遅延モードを有効にするものではありません。
自動テストと実接続検証は[READMEの開発と検証](README_ja.md#開発と検証)を参照してください。

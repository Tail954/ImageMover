# これはなに？
Stable Defusion WebUIやreforgeで生成された画像ファイルを移動、コピーするためのシンプルなアプリです。\
選択したフォルダ内の画像ファイルを、**サブフォルダ内も含めて表示** します。\
空のサブフォルダがあったら削除します。\
WebUIのデフォルト設定で作成される日付ごとのフォルダをまとめてチェックすることを想定しています。\
コピーする際は、並べやすいようにファイル名の先頭に連番をつけます。\
対応している拡張子は`png` `jpeg` `webp` です。
## 既知の問題
- 空のフォルダが入れ子になっていると最下層のフォルダしか削除されない。

## インストール
- ブランチ右上の **<>code** をクリック、 **Download ZIP** でダウンロード。
- パスに2バイト文字（日本語など）が含まれないフォルダに解凍。
- **ImageMoverRun.bat** を実行。
- **WindowsによってPCが保護されました** が表示される場合は **詳細情報** クリックで表示される`実行` をクリック。
- 依存ファイルインストール後、アプリが起動します。
## 使い方
2回目以降の起動も**ImageMoverRun.bat** を実行します。
- 起動するとフォルダ選択ダイアログが表示されます。
- 画像が保存されたフォルダを選んで`フォルダの選択` を押します。WebUIのtxt2img-images等を想定しています。
- フォルダ内に空のサブフォルダがある場合、削除するか訊いてきます。削除するとゴミ箱に移動します。
- サムネイルが表示されます。
### 移動する
- サムネイルをクリックして選択状態にします。
- 選び終わったらウィンドウ下の `Move` をクリックします。
- 移動先のフォルダ選択ダイアログが表示されます。
- フォルダを選んで`フォルダの選択` を押すと移動します。
### コピーする
- ウィンドウ右上の `Copy Mode` をクリックします。ボタンが `Copy Mode Exit` に変わり、コピーモードになります。
- コピーしたいファイルを **コピーしたい順番に** クリックで選択します。選択すると番号が振られます。
- ウィンドウ右下の `Copy` をクリックします。
- フォルダ選択ダイアログが表示されます。
- コピー先のフォルダを選んで`フォルダの選択` を押すと、 `振られた番号3桁` + `_` + `元のファイル名` でコピーされます。
- コピー先に連番付きのファイルが既にある場合、続きから番号が振り直されます。
- `Copy Mode Exit` をクリックするとコピーモードを終了します。
## その他の機能
### フォルダツリー
  - フォルダをクリックするとその中のファイルをサムネイルに表示。 **選択は解除** されます。
  - 使わないときは `<<` クリックで非表示にするとサムネイル列数+1。
### `-` `+` ボタン
  - サムネイルの列数変更。真ん中に現在の列数を表示。
### フィルタ
  - メタデータに含まれる情報でフィルタする。
    - テキストボックス
      -  `,（カンマ）` 区切りで複数のテキスト入力可。空白で `Filter` を押すとフィルタ解除。
    - ラジオボタン
      - and（すべてを含む）、or（いずれかを含む）を切り替える。
### Sort by
  - ファイル名または更新日付の昇順、降順で並べ替え。
### サムネイル
  - マウスオーバーでフォルダパス表示。
  - 右クリックでメタデータ表示。
  - ダブルクリックで拡大縮小可能なプレビューウィンドウ表示。[Preview mode](#Preview-mode)
### Config
#### cache size
  - サムネイルのキャッシュサイズを変更できます。1000以上の画像ファイルがあり、動作が重いと感じたら画像の枚数以上に増やすと改善するかもしれません。増やすほどメモリを食います。初期値1000＝1000枚までキャッシュ。
#### Preview mode
  - プレビューウィンドウの表示方法を切り替えます。
    - シームレス：ウィンドウサイズに合わせて画像を拡大縮小。
    - スクロール：ウィンドウサイズには連動せず、Ctrl+スクロールで拡大縮小。ウィンドウサイズを超える場合はドラッグで移動。


# 出典・取得履歴

確認日: 2026-09-25。正確なPBF取得時刻・SHA256・OSM収録時刻は
`../processed/manifest.json` を参照。取得に失敗した場合は処理を停止する。

## 道路・形状・IC/JCT・名称

- OpenStreetMap contributors, Geofabrik Kantō:
  https://download.geofabrik.de/asia/japan/kanto.html
- 使用ファイル: https://download.geofabrik.de/asia/japan/kanto-260923.osm.pbf
- 山梨方面の補完: Geofabrik Chūbu:
  https://download.geofabrik.de/asia/japan/chubu.html
- 使用ファイル: https://download.geofabrik.de/asia/japan/chubu-260923.osm.pbf
- ライセンス: https://www.openstreetmap.org/copyright （ODbL 1.0）
- OSM-derived `nodes.json`, `road_segments.json`, `access_points.json` は派生データベース。
  © OpenStreetMap contributors。再配布時にもODbLの条件に従う。
- highway=motorway / motorway_link のWayのみを収録。motorway_junctionは名称・区間境界に使う。
  距離はOSMの各連続座標間のWGS84測地線長の和。公式営業距離の転記はしていない。
- OSMタグ仕様: https://wiki.openstreetmap.org/wiki/Tag:highway=motorway_link
  motorway_linkのoneway未指定は推測せず除外。motorway本線はOSM既定の一方通行。
- PBF処理: https://docs.osmcode.org/pyosmium/latest/user_manual/01-First-Steps/

## 使用した料金区分資料

1. NEXCO中日本「E20 中央道（八王子～高井戸）の料金について」
   https://dc2.c-nexco.co.jp/etc/discount/etc/chuodo/
   「適用区間」「適用内容と通行料金」「料金例」を確認。
   高井戸～八王子は大都市部区間の水準、八王子以西は普通区間の水準との記載。
   上野原～調布の例示に限定して、八王子～上野原をNORMALに設定。
   マスターID: `chuo-takaido-hachioji`, `chuo-chofu-hachioji`, `chuo-hachioji-uenohara`。
   調布～八王子は同じ資料内の料金例に明示される内側区間。高井戸の反対車線の
   境界点を推測せず、OSM上で確認できる調布までに限定して区分を適用する。
   区分のみ参照し、割引・上限・料金額は実装しない。
2. NEXCO中日本「中央道（高井戸～八王子）の料金について」公式説明資料
   https://www.c-nexco.co.jp/images/news/3791/8b0f4b213b822eadfefbbe3023e25052.pdf
   大都市近郊区間の水準との明示を照合。最新金額の根拠には使わない。
3. 首都高速道路「料金・ルート検索／料金・割引・ETC情報」
   https://www.shutoko.jp/tolls/
   首都高の別料金体系の根拠。OSM名称に「首都高速」が明示された区間を
   SPECIAL_SYSTEMとし、通常の経路検索では通過しない。
   未命名ランプに首都高の区分を自動伝播しない。

## 調査したがマスターへ未採用の資料

- NEXCO東日本「新たな高速道路料金」2014年資料:
  https://www.e-nexco.co.jp/rest/pressroom/press_release/head_office/h26/0314/pdfs/00.pdf
  3料金水準の背景確認用。対象時期・適用条件の異なる過去資料なので、
  他路線の現在の境界や普通区間の自動割当てに利用していない。
- 国土交通省の区間境界資料は今回のマスターには未使用。
- ETC割引の「東京近郊」対象区間一覧を、そのまま料金水準の区分として流用しない。

## 境界の解釈と未確認情報

料金区分マスターのIC境界は公式資料に基づく。OSMへの位置合わせは
同名motorway_junctionの有向本線上の接続点を使用する。公式課金距離の
起終点・ETCアンテナ位置との同一性までは確認できていない。
そのためこの成果物は道路形状距離の集計サンプルであり、正式な料金計算用
営業距離データではない。ランプと区分未確認区間はUNKNOWN。
OSM上の境界が見つからない場合や本線に複数経路がある場合は区分を適用せず、
`quality_report.json` にunresolvedを残す。異なる区分が競合するエッジはUNKNOWN。


## 実際に残した境界の競合

八王子ICはOSM上で第1出口・第2出口・反対車線の分岐点に分かれる。
複数候補からの区間割当てが重複する `segment:729` はNORMALとMETROPOLITANが
競合するためUNKNOWNとした。公式資料だけではどの形状点を厳密な課金境界に
すべきか確定できず、座標や按分距離を推測していない。
高井戸の西向き境界はOSMの同名分岐点で確認できないため、当該方向では
調布より東へMETROPOLITANを延長していない。

OSM取得日は両ファイルとも2026-09-25。OSM収録時点は両方とも
2026-09-23T20:22:04Z。ダウンロードスクリプトの `--manifest` オプションで、
Git管理したSHA256と再取得ファイルの一致を検証できる。

# 関東高速道路グラフ

OSMから有向の高速道路ネットワークを生成し、入口IC・出口ICを指定して
道路区間と形状距離を返すPythonサンプルです。料金計算は行いません。
公式資料に基づく区分マスターを別管理し、未確認区間は `UNKNOWN` のまま集計します。

**算出値は道路形状に沿った距離で、NEXCOの公式営業距離ではありません。**
料金区分のIC境界をOSMの分岐点へ対応付けていますが、正式な課金起終点との
一致は未検証です。後段の料金計算プログラムへ接続する場合にも、UNKNOWNを
普通区間として扱わず、営業距離との違いを保持してください。

## 再現手順

Python 3.11以上、インターネット接続、PBF約1GBと作業領域が必要です。

```bash
git clone https://github.com/fumiumi/highway-charge-calculator.git
cd highway-charge-calculator
git switch feature/kanto-highway-graph
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

# 日付を固定したGeofabrik関東・中部PBFを取得し、提供元MD5を検証
python scripts/download_osm_data.py --regions kanto chubu --snapshot 260923 \
  --manifest data/processed/manifest.json

# 西端・南端・東端・北端。山梨方面を含む関東周辺を抽出
python -m src.main build \
  data/raw/kanto-260923.osm.pbf data/raw/chubu-260923.osm.pbf \
  --bbox 138.25 34.75 141.25 37.25

python -m pytest -q
python -m scripts.run_samples --check
python -m src.main route 調布IC 国立府中IC
```

同等のコマンド: `make install download-data build test samples`。
Windowsでは仮想環境の有効化を `.venv\Scripts\activate` に変更してください。
最新データを使う場合は `--snapshot latest` を指定できますが、同じ結果の再現には
日付固定版と `data/processed/manifest.json` のSHA256を使用してください。
Geofabrik側で過去ファイルが提供されなくなった場合は取得エラーで停止します。
データを別途保管する場合もGitには入れず、ハッシュが一致するファイルを使用してください。

加工済みJSONはGitに含めるため、clone後に依存関係を導入するだけでも検索・テストできます。
データ生成の再現確認には上記のPBF取得とbuildが必要です。

## Python API

```python
from src.route_finder import find_route, aggregate_distance_by_section

route = find_route("調布IC", "国立府中IC")
for segment in route:
    print(segment.road_name, segment.distance_km, segment.section_type.name)
print(aggregate_distance_by_section(route))
```

`find_route` はカレントディレクトリの `data/processed` を読みます。
他のディレクトリを使う場合:

```python
from src.storage import load_graph
from src.route_finder import RouteFinder

graph, nodes, access = load_graph("data/processed")
finder = RouteFinder(graph, nodes, access)
route = finder.find_route("調布IC", "国立府中IC")
```

既定は `mode="access"`。OSMの `motorway_link` と一般道の接続点を入口・出口とし、
入口・出口のランプも距離に含めます。入口候補が同名の複数ランプにある場合は
走行可能な候補のうち最短を選びます。上下線のノード同士を接続し直しません。
一般道路は走行しません。途中で一般道へ降りて再流入する経路も許可しません。
名称や接続が欠落しているICは `RouteNotFound`、存在しない名称は `UnknownIC` を返します。

`mode="junction"` / CLI `--mode junction` はOSM本線上の同名分岐点間の
検証用検索です。ICの実際の入口・出口からの走行可能性を保証せず、ランプ距離を含みません。
既定検索が失敗しても、このモードへ自動で切り替えません。

## ディレクトリとデータモデル

```text
src/
  models.py          RoadNode / RoadSegment / SectionType / TollSectionRule
  osm_loader.py      OSM PBF/XMLの2パス読み取り・通行条件の保守的除外
  graph_builder.py   接続を保存した有向MultiDiGraph・測地線距離計算
  names.py           名称正規化・OSMの言語別名
  access_points.py   ランプ接続とOSM料金所名から入口・出口を解決
  route_finder.py    ターン制約付きDecimal距離最短探索・区分別集計
  toll_sections.py   出典付き区分マスターの適用
  storage.py         JSON読み書き
  validation.py      構造検査
  main.py            CLI
scripts/
  download_osm_data.py
  run_samples.py
data/
  raw/               生PBF・ダウンロード履歴（Git対象外）
  master/            人が確認する料金区分マスター
  processed/         グラフ・適用済みマスター・品質報告・実行例
  sources/sources.md  出典・解釈・取得方法
```

IC/JCTを区間境界として保持します。ただし、上下線・JCTの複数ランプを単一地点へ
潰すと存在しない経路ができるため、OSMノードIDごとの接続点を維持します。
名称のない分岐・合流、道路名変更点には `TOPOLOGY`、一般道との接続点には
`ACCESS_BOUNDARY`、料金所には `TOLL_GATE` を使用します。IC/JCTを捏造して補いません。
単純な途中形状点は縮約し、複数Wayを一つのRoadSegmentへまとめます。
このため区間列にはIC/JCT間の本線に加え、接続維持に必要な短い区間も含まれます。

距離は全OSM形状点間のWGS84楕円体測地線長を合算したkmをDecimalで保持し、JSONでは
文字列として保存します。途中の丸めは行わず、表示時のみ必要な桁数へ丸めてください。
`osm_way_ids` と順序付き `osm_node_ids` により、元の道路形状を追跡できます。
名称正規化はIC/インターチェンジ・JCT/ジャンクション・全半角・空白を扱います。
英語表記はOSMの `name:en` 等に存在する場合に解決し、翻訳の推測はしません。
OSMの `wikipedia=ja:…インターチェンジ` / `…ジャンクション` タグを名称の別表記として
使い、八王子の第1・第2出口を同一ICの候補として解決します。ICとJCTは混同しません。
入口と出口のランプが離れていても、OSM料金所名がIC名と一致するときは入口候補を
関連付けます。物理ノードを結合したり、近接距離だけで接続を補ったりはしません。
10kmを超えて離れた同名候補は曖昧としてエラーにします。

## 料金区分マスター

`data/master/toll_section_rules.json` に道路名、起終点、区分、公式資料URL、資料名、
確認日、解釈を記録しています。現状は中央道の確認できた範囲のみです。

| 区間 | 区分 | 根拠 |
|---|---|---|
| 中央道 高井戸～八王子 | METROPOLITAN | NEXCO中日本・中央道料金案内 |
| 中央道 調布～八王子 | METROPOLITAN | 同案内の八王子～調布料金例。高井戸の反対車線境界を推測せず内側で適用 |
| 中央道 八王子～上野原 | NORMAL | 同案内の八王子以西の記載と上野原～調布の料金例 |
| 首都高速とOSM名称で確認できる区間 | SPECIAL_SYSTEM | 首都高速公式料金案内 |
| 上記以外・未命名ランプ・未解決境界 | UNKNOWN | 推測しない |

`SPECIAL` をデータモデルと集計でサポートしますが、特別区間の公式境界を
今回のOSMへ検証して対応付けていないため、マスターへの登録はしていません。
SPECIAL_SYSTEMと確認できた首都高区間は既定の検索では除外します。
首都高への所属がOSM名称から確認できない無名ランプ等はUNKNOWNのため、
すべての所属区間の識別を保証するものではありません。必要時だけPython APIの
`allow_special_system=True` で許可できます。

道路名はOSMの高速道路を示す `route=road` リレーションが一意ならそれを使用し、
上り・下りの接尾辞を除きます。元の橋名などは `osm_names`、根拠リレーションは
`osm_route_relation_ids` に保存します。リレーションが競合する場合はWayの名前を使い、
警告を記録します。抽出対象の路線を固定リストで制限するものではありません。

区分適用は同一道路名・motorway本線の唯一の有向経路に限定します。
境界が見つからない・複数本線経路がある場合は適用せず `unresolved` を報告し、
異なる区分が競合した場合は `UNKNOWN` とします。ランプに区分を伝播しません。
公式資料の営業距離とOSM距離が異なっても、公式距離でジオメトリを上書きしません。
出典の詳細は [sources.md](data/sources/sources.md) を参照してください。

## 制約・今後の拡張

- 料金額、割引、車種、ETC条件、公式営業距離、最安料金経路は未実装。
- 通行止めやリアルタイム規制は反映しません。実走行のナビゲーション用途ではありません。
- OSMの接続・名称・highwayタグの品質に依存します。highway=trunk等で登録された
  自動車専用道路、未開通・工事中道路は対象外です。
- motorway_linkのoneway不明、条件付き通行、方向別アクセス等は除外します。
  OSMの単一via-nodeの `no_*` / `only_*` 制限は到着Way・直前ノードを状態に持って
  探索時に判定します。via-wayや条件付きなど未対応の制限はfrom Wayを保守的に
  除外します。合法な別方向まで通れなくなる場合があり、完全対応は今後の拡張対象です。
- 地域境界を跨ぐWayはbbox内に全座標が入るものだけ採用します。
  境界付近の経路欠損を補完せず、必要ならbboxを広げて再生成してください。
- ランプが一般道やserviceとして登録されているICや、同じランプ成分に複数IC名が
  混在する場合は入口・出口を解決できません。未知の接続を距離近接で補いません。
- 今後は公式資料による他路線の区分マスター拡充、課金起終点の独立管理、
  via-wayの制約状態付き探索、確認済み名称別名マスター、経由地点・実走行経路に拡張できます。
  経由地点追加時も上下線間に架空の乗り換えを作らない設計が必要です。

## Git管理とセキュリティ

作業ブランチは `feature/kanto-highway-graph`。main/masterへの直接コミットはしません。
`.gitignore` は生データ、仮想環境、キャッシュ、一時ファイル、`.env` を除外します。
この実装にはAPIキーや認証情報は不要です。生PBFを含めず、加工済みJSONと再取得スクリプトを管理します。

OSM由来データ: © OpenStreetMap contributors, [ODbL 1.0](https://www.openstreetmap.org/copyright)。
公式資料自体のコピーは収録せず、出典URLと確認した区間のマスターを保存しています。

## 実データ検証結果・Phase報告

2026-09-23 20:22:04 UTC時点の関東・中部OSM抽出から、12,646ノード、19,303区間を生成。
加工済みデータは約17MB（最大ファイル約13MB）で、出典・ハッシュとともにGit管理します。

| Phase | 実施結果 | 制約・UNKNOWN |
|---|---|---|
| 1 中央道 | 本線に接続する27種のIC/JCT名を収録。入口・出口を指定した検索を検証 | ランプ・公式課金起終点は未確認 |
| 2 主要路線 | 東名、新東名、中央、関越、東北、常磐、館山の抽出を自動テスト | 路線ごとの全IC組合せは未検証。中央道以外の料金区分はUNKNOWN |
| 3 環状道路 | 圏央道・外環を収録。八王子JCTを経由する中央道→圏央道を実行 | 外環経由の全接続は未検証 |
| 4 料金区分 | 公式資料に基づく中央道の3ルールを適用 | 広域マスターは未完成。八王子の複数出口間1区間の競合はUNKNOWN |

経路例（km、表示のみ小数第3位へ丸め）:

| 入口 → 出口 | 総距離 | NORMAL | METROPOLITAN | UNKNOWN |
|---|---:|---:|---:|---:|
| 調布 → 国立府中 | 10.211 | 0.000 | 8.320 | 1.890 |
| 調布 → 上野原 | 43.422 | 24.230 | 16.780 | 2.412 |
| 調布 → 相模原（八王子JCT経由） | 37.622 | 9.881 | 16.780 | 10.961 |

SPECIAL / SPECIAL_SYSTEM は上記3例では0です。調布→国立府中は本線部分が同一料金区分の例ですが、
ランプはUNKNOWNです。区分別に丸めた値の合計は、丸めた総距離と一致しない場合があります。
追加で `python -m src.main route 調布IC 甲府昭和IC` も実行し、106.848 kmの経路を確認しました。
上野原以西を普通区間と推測して自動補完していないため、この経路には65.838 kmのUNKNOWNが含まれます。

自動テストは32件成功。3例の再実行と保存済みJSONの完全一致も確認しています。
品質報告は `data/processed/quality_report.json`、各区間の具体的な経路は
`data/processed/sample_routes.json`、右左折制限は `data/processed/turn_restrictions.json` を参照してください。

未確認区間は18,423区間。NORMAL 19区間、METROPOLITAN 21区間、SPECIAL_SYSTEM 840区間です。
OSMの複数路線名338件、未対応ターン制限によるWay除外99件、oneway不明33件、
条件付き・可変通行21件、アクセス制限10件、曖昧なランプ成分25件を品質報告へ記録しました。
これらの数には抽出bbox外の入力Wayに対する警告も含まれ、グラフの全接続を保証するものではありません。

リポジトリは空の状態から開始しています。比較元main/masterが存在しないため、
本作業の成果は作業ブランチへ保存します。PRに必要な実装内容・出典・生成手順・対応範囲・
テスト・制約・UNKNOWN・拡張候補はこのREADMEとsources.mdに記載しています。

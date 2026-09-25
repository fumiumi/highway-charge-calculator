import json
from pathlib import Path
import subprocess
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]


def run(*arguments, module='src.main', input=None):
    return subprocess.run([sys.executable,'-m',module,*arguments],cwd=ROOT,input=input,text=True,capture_output=True)


def test_real_unpriced_route_outputs_distances_and_no_fee():
    result=run('fee','--vehicle','REGULAR','--start','調布IC','--end','上野原IC','--json')
    assert result.returncode==2
    report=json.loads(result.stdout)
    assert report['status']=='unpriced'
    assert report['fee_yen'] is None
    assert report['unpriced_sections']==['UNKNOWN']
    assert report['distances_km']['UNKNOWN'].startswith('2.412')


def test_real_estimate_with_explicit_unknown_unit_price():
    result=run('fee','--vehicle','普通車','--start','調布IC','--end','上野原IC','--unknown-unit-price','24.60','--json')
    assert result.returncode==0,result.stderr
    report=json.loads(result.stdout)
    assert report['fee_yen']==1430
    assert report['status']=='estimate'
    assert report['billed_distances_km']=={'NORMAL':'24.2','METROPOLITAN':'16.8','SPECIAL':'0.0','SPECIAL_SYSTEM':'0.0','UNKNOWN':'2.4'}
    assert report['terminal_charge_yen']=='150'
    assert report['user_unit_prices_yen_per_km']=={'UNKNOWN':'24.60'}


def test_same_ic_is_zero_without_terminal_charge():
    result=run('fee','--vehicle','2','--start','調布IC','--end','調布IC','--json')
    assert result.returncode==0
    assert json.loads(result.stdout)['fee_yen']==0
    assert json.loads(result.stdout)['terminal_charge_yen']=='0'


@pytest.mark.parametrize('flags',[
    ['--vehicle','invalid','--start','調布IC','--end','国立府中IC'],
    ['--vehicle','REGULAR'],
    ['--vehicle','REGULAR','--start','不存在IC','--end','国立府中IC'],
    ['--vehicle','REGULAR','--start','八王子JCT','--end','国立府中IC'],
    ['--vehicle','REGULAR','--start','調布IC','--end','国立府中IC','--data','does-not-exist'],
])
def test_json_input_errors(flags):
    result=run('fee',*flags,'--json')
    assert result.returncode==2
    assert json.loads(result.stdout)['status']=='error'
    assert 'Traceback' not in result.stderr


def test_interactive_entrypoint():
    result=run('--unknown-unit-price','24.60',module='src.fee_cli',input='2\n調布IC\n上野原IC\n')
    assert result.returncode==0,result.stderr
    assert '最終料金（概算・税込）: 1,430円' in result.stdout
    assert '未確認 (UNKNOWN)' in result.stdout


@pytest.mark.parametrize('price',['NaN','Infinity','-1','abc'])
def test_bad_cli_price(price):
    result=run('fee','--vehicle','2','--start','調布IC','--end','国立府中IC','--unknown-unit-price',price)
    assert result.returncode==2
    assert 'Traceback' not in result.stderr

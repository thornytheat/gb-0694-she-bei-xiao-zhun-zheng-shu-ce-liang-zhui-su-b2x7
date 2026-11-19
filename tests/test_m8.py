import csv, io
from decimal import Decimal
from app.pipeline import calculate
from app.config import SAMPLE, HEADERS, DECLARATION_COVERAGE_K
from app.domain import combine_uncertainty, guard_band_verdict
from app.numeric import number

# ---------- 样本总体口径 ----------

def test_sample_declaration_partition(ctx):
    metrics = {m[0]: m[1] for m in ctx['stages']['8']['metrics']}
    assert metrics == {'出具声明': 33, '停止出具': 10, '符合': 29, '不符合': 1, '无法判定': 3}
    # 守恒：出具 + 阻断 = 全部测量
    assert metrics['出具声明'] + metrics['停止出具'] == len(ctx['measurements'])

def test_three_verdicts_all_traceable(ctx):
    for row in ctx['stages']['8']['rows']:
        assert row['溯源路径'] and row['原因码'] and row['允许偏差_V']
        if row['判定'] != '停止出具':
            assert row['声明编号'].startswith('DCL-') and row['来源证书'] != '—'

# ---------- 不确定度缺失不得按零 ----------

def test_missing_uncertainty_is_undetermined_not_zero(ctx):
    row = next(r for r in ctx['stages']['8']['rows'] if r['证书'] == 'C0040')
    assert row['判定'] == '无法判定'
    assert row['原因码'].startswith('UNCERTAINTY_MISSING') and 'C0040' in row['原因码']
    assert row['扩展不确定度U_V'] == '缺失' and row['合成标准不确定度_V'] == '缺失'
    record = next(d for d in ctx['declarations'] if d['cert'] == 'C0040')
    assert record['expanded_u_v'] is None and record['uc_v'] is None  # 没有被默认为0

def test_missing_uncertainty_still_registered_for_recalculation(ctx):
    # 无法判定也是正式声明，带编号登记，上游补录后可重算追溯
    assert any(d['cert'] == 'C0040' for d in ctx['declarations'])

# ---------- 整链去重与RSS合成 ----------

def test_shared_reference_counted_once(ctx):
    record = next(d for d in ctx['declarations'] if d['cert'] == 'C0050')
    assert record['sources'] and [s['证书'] for s in record['sources']] == ['C0050', 'C0005', 'ROOT']
    # sqrt(0.1^2 + 0.1^2 + 0.05^2) = 0.15，去重后每份证书只计一次
    assert Decimal(record['uc_v']) == Decimal('0.15')
    assert Decimal(record['expanded_u_v']) == Decimal('0.3')
    # 朴素逐跳线性累加基线保留作对照，证明去重修正的幅度
    assert Decimal(record['naive_linear_uc_v']) == Decimal('0.25')

def test_combine_dedupes_repeated_cert(ctx):
    path = ['X', 'ROOT', 'ROOT', 'X']  # 同一上级在多级证书中重复出现
    certs = dict(ctx['certs'])
    certs['X'] = {'unc_v': '0.2', 'unc_missing': False, 'coverage_k': '2'}
    uc, sources, missing, linear = combine_uncertainty(path, certs)
    assert [s['证书'] for s in sources] == ['X', 'ROOT']
    assert uc == (Decimal('0.2') ** 2 + Decimal(certs['ROOT']['unc_v']) ** 2).sqrt()

def test_combine_reports_missing(ctx):
    uc, sources, missing, linear = combine_uncertainty(['C0040', 'C0020', 'ROOT'], ctx['certs'])
    assert uc is None and missing == ['C0040'] and linear is None

# ---------- 护基判定三态 ----------

def test_guard_band_verdicts():
    v = number('5'); lo, hi = number('4'), number('6'); u = number('0.2')
    assert guard_band_verdict(v, lo, hi, u) == '符合'
    assert guard_band_verdict(number('6.5'), lo, hi, u) == '不符合'
    assert guard_band_verdict(number('5.95'), lo, hi, u) == '无法判定'

def test_guard_band_boundary_tangent_is_conform():
    # 区间与规格限相切：不拒绝原假设，判符合
    assert guard_band_verdict(number('5.8'), number('4'), number('6'), number('0.2')) == '符合'

def test_nonconform_and_inconclusive_samples(ctx):
    rows = {r['证书']: r for r in ctx['stages']['8']['rows']}
    assert rows['C0005']['判定'] == '不符合'
    assert rows['C0006']['判定'] == '无法判定' and rows['C0006']['原因码'] == '无法判定'
    assert rows['C0050']['判定'] == '无法判定'

# ---------- 失效/超量程/断链停止出具 ----------

def test_blocked_measurements_get_no_declaration(ctx):
    blocked = [r for r in ctx['stages']['8']['rows'] if r['判定'] == '停止出具']
    assert {r['证书'] for r in blocked} >= {'C0007', 'END', 'C0004', 'C0024', 'C0002', 'C0022'}
    assert all(r['声明编号'] == '—' for r in blocked)
    blocked_certs = {r['证书'] for r in blocked}
    assert all(d['cert'] not in blocked_certs for d in ctx['declarations'])

def test_out_of_range_blocks_before_uncertainty(ctx):
    row = next(r for r in ctx['stages']['8']['rows'] if r['证书'] == 'C0007')
    assert row['原因码'] == 'OUT_OF_RANGE'

# ---------- 来源与共同系统分量可追溯 ----------

def test_sources_and_common_components_shown(ctx):
    row = next(r for r in ctx['stages']['8']['rows'] if r['证书'] == 'C0025')
    assert row['来源证书'] == 'C0025、C0005、ROOT'
    assert 'ROOT' in row['共同系统分量']  # ROOT被全批共享，标为共同系统分量而非随机抵消

def test_manifest_records_uncertainty_policy(ctx):
    params = ctx['manifest']['parameters']
    assert params['包含因子k'] == DECLARATION_COVERAGE_K
    assert 'RSS' in params['不确定度合成']

# ---------- 输入解析：缺失/非法不确定度 ----------

def _csv_with(extra_rows):
    rows = list(csv.DictReader(io.StringIO(SAMPLE.read_text(encoding='utf-8-sig'))))
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=HEADERS)
    writer.writeheader()
    base = {h: '' for h in HEADERS}
    for r in rows + [{**base, **e} for e in extra_rows]:
        writer.writerow(r)
    return out.getvalue()

def _valid_row(cert, **over):
    row = {'cert': cert, 'device': 'D-' + cert, 'parent': 'ROOT', 'valid_from': '2026-01-01',
           'valid_to': '2027-01-01', 'minimum': '0', 'maximum': '10', 'unit': 'V', 'revoked': 'no',
           'measured_at': '2026-11-17', 'value': '5', 'measure_unit': 'V', 'version': '1',
           'uncertainty': '0.1', 'unc_unit': 'V', 'coverage_k': '2'}
    row.update(over)
    return row

def test_negative_uncertainty_isolated():
    result = calculate(_csv_with([_valid_row('NEGU', uncertainty='-0.1')]))
    assert any(q['cert'] == 'NEGU' and q['原因码'] == 'RANGE' for q in result['quarantine'])

def test_uncertainty_without_unit_isolated():
    result = calculate(_csv_with([_valid_row('NOUNIT', unc_unit='')]))
    assert any(q['cert'] == 'NOUNIT' and q['原因码'] == 'MISSING' for q in result['quarantine'])

def test_bad_coverage_factor_isolated():
    result = calculate(_csv_with([_valid_row('BADK', coverage_k='0')]))
    assert any(q['cert'] == 'BADK' and q['原因码'] == 'COVERAGE' for q in result['quarantine'])

def test_half_spec_pair_isolated():
    result = calculate(_csv_with([_valid_row('HSPEC', spec_min='4')]))
    assert any(q['cert'] == 'HSPEC' and q['原因码'] == 'SPEC' for q in result['quarantine'])

def test_blank_spec_falls_back_to_calibrated_range(ctx):
    record = next(d for d in ctx['declarations'] if d['cert'] == 'C0001')
    assert record['spec_lo_v'] == '0' and record['spec_hi_v'] == '10'

# ---------- 登记、幂等与上游重算 ----------

def test_rerun_same_batch_creates_no_second_declaration(client):
    first = client.post('/api/run', json={}).get_json()
    again = client.post('/api/run', json={}).get_json()
    assert again['reused'] is True
    items = client.get('/api/declarations').get_json()
    assert len(items) == first['declarations_registered']
    assert len({d['id'] for d in items}) == len(items)
    run_items = client.get('/api/declarations?run_id=' + first['manifest']['run_id']).get_json()
    assert len(run_items) == len(items)

def test_upstream_update_supersedes_old_declaration(client, raw):
    first = client.post('/api/run', json={'csv': raw}).get_json()
    old = next(d for d in client.get('/api/declarations').get_json() if d['cert'] == 'C0001')
    # 上游记录更新：ROOT的不确定度变化，内容摘要变化形成新批次
    updated = raw.replace('ROOT,REF-001', 'ROOT,REF-001', 1)
    updated = updated.replace('100,V,1,0.05,V,2', '100,V,1,0.08,V,2', 1)
    second = client.post('/api/run', json={'csv': updated}).get_json()
    assert second['manifest']['run_id'] != first['manifest']['run_id']
    items = client.get('/api/declarations').get_json()
    old_now = next(d for d in items if d['id'] == old['id'])
    assert old_now['status'] == '已重算' and old_now['superseded_by']
    new_one = next(d for d in items if d['id'] == old_now['superseded_by'])
    assert new_one['status'] == '有效' and new_one['record']['input_sha256'] == second['manifest']['sha256']
    # 状态过滤
    assert all(d['status'] == '有效' for d in client.get('/api/declarations?status=有效').get_json())

def test_evidence_csv_contains_declaration_stage(client):
    client.post('/api/run', json={})
    text = client.get('/api/evidence.csv').data.decode('utf-8-sig')
    assert '符合性声明' in text and 'DCL-' in text and '扩展不确定度U_V' in text

def test_m8_endpoint_serves_declarations(client):
    payload = client.post('/api/m8', json={}).get_json()
    assert payload['stage'] == 8 and len(payload['declarations']) == 33

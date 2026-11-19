import hashlib
from collections import Counter
from decimal import Decimal
from app.config import DECLARATION_COVERAGE_K
from app.domain import combine_uncertainty, guard_band_verdict
from app.numeric import number, serial

DISPLAY_PLACES = '0.000001'

def q6(value):
    if value is None:return None
    return str(Decimal(value).quantize(Decimal(DISPLAY_PLACES)))

def declaration_id(run_id, line_no):
    return 'DCL-' + hashlib.sha256((run_id + ':' + str(line_no)).encode('utf-8')).hexdigest()[:12].upper()

def apply(ctx):
    k = number(str(DECLARATION_COVERAGE_K))
    # 预计算每份证书在本批多少条测量的溯源链中出现：>1 即共同系统分量
    usage = Counter()
    for m in ctx['measurements']:
        for node in set(ctx['chains'][m['cert']]['path']):
            usage[node] += 1
    declarations = []          # 结构化声明（仅实际出具的声明；阻断项不出具）
    rows = []                  # 页面/证据用中文行（含阻断与无法判定，保证三态可追溯）
    blocked = undetermined = conforming = nonconforming = inconclusive = 0
    for r in ctx['measurements']:
        chain = ctx['chains'][r['cert']]
        blockers = []
        if not r['window_valid']: blockers.append('INVALID_WINDOW')
        if not r['range_valid']: blockers.append('OUT_OF_RANGE')
        if not chain['valid']: blockers.append(chain['code'])
        base = {
            'run_id': ctx['manifest']['run_id'], '行号': r['行号'], '证书': r['cert'],
            '设备': r['canonical'], '测量日': r['measured_at'], '测量值_V': r['value_v'],
            '溯源路径': ' → '.join(chain['path']),
        }
        if blockers:
            # 证书失效或超量程（或溯源链断裂）：停止出具声明，不生成声明编号
            blocked += 1
            rows.append({**base, '声明编号': '—', '判定': '停止出具', '原因码': ','.join(blockers),
                         '合成标准不确定度_V': '—', '扩展不确定度U_V': '—', '声明区间_V': '—',
                         '允许偏差_V': '—', '来源证书': '—', '共同系统分量': '—'})
            continue
        uc, sources, missing, linear = combine_uncertainty(chain['path'], ctx['certs'])
        spec_lo = number(r['spec_lo_v']) if r['spec_lo_v'] is not None else number(r['min_v'])
        spec_hi = number(r['spec_hi_v']) if r['spec_hi_v'] is not None else number(r['max_v'])
        value = number(r['value_v'])
        source_names = [s['证书'] for s in sources]
        if missing:
            # 不确定度缺失不能默认成零：无法判定，仍出具带编号声明以便追溯与后续重算
            undetermined += 1
            verdict, reason = '无法判定', 'UNCERTAINTY_MISSING:' + ','.join(missing)
            expanded = interval_lo = interval_hi = None
            uc_text = u_text = interval_text = '缺失'
        else:
            expanded = uc * k
            interval_lo, interval_hi = value - expanded, value + expanded
            verdict = guard_band_verdict(value, spec_lo, spec_hi, expanded)
            reason = verdict
            if verdict == '符合': conforming += 1
            elif verdict == '不符合': nonconforming += 1
            else: inconclusive += 1
            uc_text, u_text = q6(uc), q6(expanded)
            interval_text = '[' + q6(interval_lo) + ', ' + q6(interval_hi) + ']'
        ident = declaration_id(ctx['manifest']['run_id'], r['行号'])
        record = serial({
            'declaration_id': ident, 'run_id': ctx['manifest']['run_id'], 'line_no': r['行号'],
            'cert': r['cert'], 'device': r['canonical'], 'measured_at': r['measured_at'],
            'value_v': str(value), 'verdict': verdict, 'reason_code': reason,
            'trace_path': chain['path'],
            'uc_v': None if uc is None else str(uc),
            'expanded_u_v': None if expanded is None else str(expanded),
            'coverage_k': str(k),
            'interval_lo_v': None if interval_lo is None else str(interval_lo),
            'interval_hi_v': None if interval_hi is None else str(interval_hi),
            'spec_lo_v': str(spec_lo), 'spec_hi_v': str(spec_hi),
            'sources': sources, 'missing_uncertainty': missing,
            'naive_linear_uc_v': None if linear is None else str(linear),
            'rule_version': ctx['manifest']['rule_version'],
            'input_sha256': ctx['manifest']['sha256'],
        })
        declarations.append(record)
        shared = '、'.join(sorted(s for s in source_names if usage[s] > 1)) or '无'
        rows.append({**base, '声明编号': ident, '判定': verdict, '原因码': reason,
                     '合成标准不确定度_V': uc_text, '扩展不确定度U_V': u_text,
                     '声明区间_V': interval_text,
                     '允许偏差_V': '[' + q6(spec_lo) + ', ' + q6(spec_hi) + ']',
                     '来源证书': '、'.join(source_names) if source_names else '—',
                     '共同系统分量': shared})
    ctx['declarations'] = declarations
    return {'rows': rows, 'declarations': declarations,
            'metrics': [['出具声明', len(declarations), '份'], ['停止出具', blocked, '条'],
                        ['符合', conforming, '份'], ['不符合', nonconforming, '份'],
                        ['无法判定', undetermined + inconclusive, '份']]}

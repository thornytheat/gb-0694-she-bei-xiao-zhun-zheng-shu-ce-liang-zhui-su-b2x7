from app.domain import day,equivalence,volts
from app.numeric import number
from app.errors import DomainError
from app.reasons import isolate

def optional_volts(raw_value, raw_unit, cert_unit, label):
    """可选电压量：缺失返回None（不得当作零），给值则按证书单位归一化到V。"""
    text=(raw_value or '').strip()
    if not text or text.upper() in ('-','N/A','NULL','未知'):
        return None
    unit=(raw_unit or '').strip() or cert_unit
    try:
        return volts(text, unit)
    except DomainError:
        raise DomainError('NUMBER', label+'数值或单位无效')

def apply(ctx):
    certs={};measurements=[];seen=set();duplicates=0;conflicted=set()
    fields=('device','parent','valid_from','valid_to','minimum','maximum','unit','revoked','version','uncertainty','unc_unit','coverage_k','spec_min','spec_max')
    for r in ctx['rows']:
        try:
            if not r['cert'] or not r['device']:raise DomainError('MISSING','证书或设备为空')
            start,end=day(r['valid_from']),day(r['valid_to']);day(r['measured_at']);value=volts(r['value'],r['measure_unit']);minimum=volts(r['minimum'],r['unit']);maximum=volts(r['maximum'],r['unit'])
            if start>=end or minimum>maximum:raise DomainError('RANGE','证书区间无效')
            if r['revoked'] not in ('yes','no'):raise DomainError('REVOKED_FLAG','撤销标识无效')
            if r['version']!='1':raise DomainError('VERSION','不支持的证书版本')
            # 校准不确定度：标准不确定度u（与证书同量纲），允许缺失，缺失绝不能按零参与合成
            u_raw=(r.get('uncertainty') or '').strip()
            if u_raw and not (r.get('unc_unit') or '').strip():
                raise DomainError('MISSING','给出不确定度时必须填写其单位')
            unc_v=optional_volts(r.get('uncertainty'), r.get('unc_unit'), r['unit'], '不确定度')
            if unc_v is not None and unc_v<0:raise DomainError('RANGE','不确定度不得为负')
            k_text=(r.get('coverage_k') or '').strip()
            if not k_text or k_text.upper() in ('-','N/A','NULL','未知'):
                k_value=None
            else:
                try: k_value=number(k_text)
                except DomainError: raise DomainError('COVERAGE','包含因子格式无效')
                if k_value<=0:raise DomainError('COVERAGE','包含因子必须为正')
            # 允许偏差（规格限）：可空，空则声明时回退到校准量程上下限
            spec_lo=optional_volts(r.get('spec_min'), r['unit'], r['unit'], '允许偏差下限')
            spec_hi=optional_volts(r.get('spec_max'), r['unit'], r['unit'], '允许偏差上限')
            if (spec_lo is None)!=(spec_hi is None):raise DomainError('SPEC','允许偏差上下限必须同时给出')
            if spec_lo is not None and spec_lo>spec_hi:raise DomainError('SPEC','允许偏差区间无效')
            item={**r,'value_v':str(value),'min_v':str(minimum),'max_v':str(maximum),
                  'unc_v':None if unc_v is None else str(unc_v),
                  'unc_missing':unc_v is None,
                  'coverage_k':None if k_value is None else str(k_value),
                  'spec_lo_v':None if spec_lo is None else str(spec_lo),
                  'spec_hi_v':None if spec_hi is None else str(spec_hi)}
            if r['cert'] in certs and any(certs[r['cert']][k]!=r[k] for k in fields):conflicted.add(r['cert']);isolate(ctx,r,'CONFLICT','同证书定义冲突');continue
            key=(r['cert'],r['measured_at'],r['value'],r['measure_unit'])
            if key in seen:duplicates+=1;continue
            seen.add(key);certs[r['cert']]=item;measurements.append(item)
        except DomainError as e:isolate(ctx,r,e.code,e.message)
    # A conflicted certificate is never trusted for either retained or later measurements.
    for cert in conflicted:certs[cert]['conflicted']=True
    names=equivalence([r for r in measurements if r['cert'] not in conflicted])
    for r in measurements: r['canonical']=names.get(r['device'],r['device'])
    ctx.update(certs=certs,measurements=measurements,duplicates=duplicates)
    return {'rows':[{'证书':r['cert'],'设备':r['canonical'],'别名':r['alias'],'父证书':r['parent'],'标准不确定度_V':r['unc_v'] or '缺失','定义状态':'冲突' if r['cert'] in conflicted else '一致','行号':r['行号']} for r in measurements],'metrics':[['证书',len(certs),'份'],['冲突定义',len(conflicted),'份'],['重复',duplicates,'条'],['不确定度缺失',sum(1 for r in measurements if r['unc_missing']),'份']]}

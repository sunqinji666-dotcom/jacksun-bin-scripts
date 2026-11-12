#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 x-ui 备份库提取完整「面板设置 + 节点 + 客户端」配置，生成迁移恢复用文件。
用途：服务器重装系统前留档，重装后凭此还原（客户端配置完全一致）。

用法：python3 ~/.claude/scripts/gen-la-vps-config.py

2026-09-21 建立。
注意：新版 x-ui（2.9.x）的 REALITY 伪装站字段是 `target`（如 www.amd.com:443），
      不是老版的 `dest`；只取 dest 会拿到 None —— 这里两个都取做兜底。
"""
import sqlite3, json, glob, os, urllib.parse, datetime

BASE = '/Users/jacksun/.claude/backups/la-vps'
OUT = os.path.join(BASE, '迁移配置')
os.makedirs(OUT, exist_ok=True)
ADDRESS = '154.36.132.97'

db = sorted(glob.glob(os.path.join(BASE, 'x-ui-*.db')))[-1]
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row
cur = conn.cursor()


def dump(table):
    cur.execute(f"select * from {table}")
    return [dict(r) for r in cur.fetchall()]


inbounds = dump('inbounds')
panel = {r['key']: r['value'] for r in dump('settings')}
panel_users = dump('users')
traffic = {r['email']: r for r in dump('client_traffics')}
now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

result = {
    '导出时间': now,
    '来源备份库': os.path.basename(db),
    '服务器地址': ADDRESS,
    '面板设置': panel,
    '面板用户': [u.get('username') for u in panel_users],
    'inbounds': [],
}

md = [f'# 洛杉矶 VPS · 完整迁移清单\n',
      f'> 导出时间：{now}　来源：`{os.path.basename(db)}`\n',
      '> ⚠️ 含 REALITY 私钥，等同服务器身份，**不要外传**。\n',
      '\n## 一、面板设置\n',
      '| 项 | 值 |', '|---|---|',
      f'| 面板地址 | `https://{ADDRESS}:{panel.get("webPort")}{panel.get("webBasePath")}` |',
      f'| 面板端口 | `{panel.get("webPort")}` |',
      f'| 面板路径 | `{panel.get("webBasePath")}` |',
      f'| 面板用户名 | `{", ".join(u.get("username","") for u in panel_users)}` |',
      f'| 面板密码 | 存于 db 的 bcrypt 哈希，**还原 db 后原密码直接可用** |',
      f'| 证书文件 | `{panel.get("webCertFile")}` / `{panel.get("webKeyFile")}` |',
      f'| 订阅证书 | `{panel.get("subCertFile")}` / `{panel.get("subKeyFile")}` |']

links_all = []

for ib in inbounds:
    s = json.loads(ib['settings'] or '{}')
    st = json.loads(ib['stream_settings'] or '{}')
    sn = json.loads(ib['sniffing'] or '{}')
    rs = st.get('realitySettings') or {}
    inner = rs.get('settings') or {}
    pbk = inner.get('publicKey', '')
    fp = inner.get('fingerprint', 'chrome')
    spx = inner.get('spiderX', '/')
    sni = (rs.get('serverNames') or [''])[0]
    sids = rs.get('shortIds') or []
    # 新版字段是 target，老版是 dest —— 两个都取
    target = rs.get('target') or rs.get('dest')
    clients = s.get('clients') or []

    md += [f'\n## 二、入站节点：{ib["remark"]}（端口 {ib["port"]} / {ib["protocol"]}）\n',
           '| 参数 | 值 |', '|---|---|',
           f'| 协议 | VLESS + REALITY（{st.get("network","tcp")} 传输） |',
           f'| 监听端口 | `{ib["port"]}` |',
           f'| 伪装站 target | `{target}` |',
           f'| serverName / SNI | `{sni}` |',
           f'| 指纹 fingerprint | `{fp}` |',
           f'| spiderX | `{spx}` |',
           f'| **privateKey** | `{rs.get("privateKey")}` ← **重装后必须原样，否则客户端全废** |',
           f'| publicKey（客户端用） | `{pbk}` |',
           f'| shortIds（任选其一） | {", ".join("`" + x + "`" for x in sids)} |',
           f'| decryption | `{s.get("decryption","none")}` |',
           f'| sniffing | `{json.dumps(sn, ensure_ascii=False)}` |',
           f'\n### 客户端（共 {len(clients)} 个）\n']

    ib_rec = {'备注': ib['remark'], '端口': ib['port'], '协议': ib['protocol'],
              '传输网络': st.get('network'), '安全类型': st.get('security'),
              'REALITY_target': target, 'REALITY_serverName': sni,
              'REALITY_privateKey': rs.get('privateKey'),
              'REALITY_publicKey': pbk, 'REALITY_fingerprint': fp,
              'REALITY_spiderX': spx, 'REALITY_shortIds': sids,
              'decryption': s.get('decryption', 'none'), 'sniffing': sn,
              '客户端': []}

    for idx, c in enumerate(clients, 1):
        email = c.get('email', '')
        uuid_ = c.get('id', '')
        flow = c.get('flow') or ''
        sid = sids[0] if sids else ''
        tr = traffic.get(email) or {}
        up = round((tr.get('up') or 0) / 1073741824, 2)
        down = round((tr.get('down') or 0) / 1073741824, 2)
        total = c.get('totalGB') or 0
        expiry = c.get('expiryTime') or 0
        if expiry:
            exp_s = datetime.datetime.fromtimestamp(expiry / 1000).strftime('%Y-%m-%d')
        else:
            exp_s = '永不过期'

        q = {'type': 'tcp', 'security': 'reality', 'pbk': pbk,
             'fp': fp, 'sni': sni, 'sid': sid, 'spx': spx}
        if flow:
            q['flow'] = flow
        link = (f"vless://{uuid_}@{ADDRESS}:{ib['port']}?"
                f"{urllib.parse.urlencode(q)}#{urllib.parse.quote(email)}")
        links_all.append((email, link))

        ib_rec['客户端'].append({
            'email': email, 'UUID': uuid_, 'flow': flow or '无',
            'subId': c.get('subId'), '启用': bool(c.get('enable')),
            '流量上限GB': (total // 1073741824) if total else '不限',
            '到期': exp_s, '已用上传GB': up, '已用下载GB': down, '分享链接': link,
        })

        md += [f'**{idx}. `{email}`**\n',
               f'- UUID：`{uuid_}`',
               f'- flow：{("`" + flow + "`") if flow else "无"}',
               f'- 启用：{"是" if c.get("enable") else "否"}　流量上限：{"不限" if not total else str(total//1073741824)+"GB"}　到期：{exp_s}',
               f'- 已用：上传 {up}GB / 下载 {down}GB',
               f'- 分享链接（可直接导入客户端）：\n\n```\n{link}\n```\n']

    result['inbounds'].append(ib_rec)

with open(os.path.join(OUT, '完整配置.json'), 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

md += ['\n---\n\n## 三、恢复方式\n',
       '**方式一（推荐）**：重装后把备份库放回 `/etc/x-ui/x-ui.db`，节点、客户端、面板账号全部原样回来。见 `../重装恢复方案.md`。\n',
       '**方式二（手工重建）**：重装后面板新建 VLESS+REALITY 入站，照上表逐项填回——**privateKey 必须是本文档里的原值**，否则 5 个客户端链接全部要重新分发。\n']

with open(os.path.join(OUT, '节点与客户端清单.md'), 'w', encoding='utf-8') as f:
    f.write('\n'.join(md))

with open(os.path.join(OUT, '客户端链接.txt'), 'w', encoding='utf-8') as f:
    f.write(f'# 洛杉矶 VPS（{ADDRESS}）客户端链接 · 导出于 {now}\n')
    f.write('# 可直接导入 v2rayN / Shadowrocket / Flow / Nekoray 等客户端\n\n')
    for email, link in links_all:
        f.write(f'# {email}\n{link}\n\n')

print(f'✓ 来源备份库: {os.path.basename(db)}')
print(f'✓ 入站 {len(inbounds)} 个，客户端合计 {len(links_all)} 个')
print(f'✓ 伪装站 target 已正确提取: '
      f'{[i["REALITY_target"] for i in result["inbounds"]]}')
for fn in sorted(os.listdir(OUT)):
    print(f'   - {fn} ({os.path.getsize(os.path.join(OUT, fn))} 字节)')

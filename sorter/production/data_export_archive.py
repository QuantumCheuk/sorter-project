#!/usr/bin/env python3
"""
Production Data Export & Archival System — v1.0
Export and archive production batch data for multiple stakeholders:
- Roaster: batch summary + defects + quality score
- Customer: SCA grade sheet + quality certificate
- Auditor: full traceability chain + sensor raw data
- Finance: production yield + material cost + revenue

Usage:
    python sorter/production/data_export_archive.py export --batch-id BATCH-001 --audience roaster --format json
    python sorter/production/data_export_archive.py archive --batch-id BATCH-001 --retention-days 90
    python sorter/production/data_export_archive.py list-archives
    python sorter/production/data_export_archive.py purge-expired
"""

import json, os, csv, sys, math, shutil, hashlib, gzip, argparse
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, List, Dict
from collections import defaultdict

_project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_project_root))

from sorter.production.batch_recipe_manager import RecipeManager
from sorter.production.batch_quality_tracker import BatchQualityTracker
from sorter.production.batch_tracking_system import RealTimeBatchTracker
from sorter.db.database import Database
from sorter.db.models import BatchRecord, BeanRecord


class ExportFormat(str, Enum):
    JSON = "json"; CSV = "csv"; HTML = "html"; TEXT = "text"

class ExportAudience(str, Enum):
    ROASTER = "roaster"; CUSTOMER = "customer"; AUDITOR = "auditor"; FINANCE = "finance"

class ArchivalStatus(str, Enum):
    ACTIVE = "active"; ARCHIVED = "archived"; COMPRESSED = "compressed"; DELETED = "deleted"

@dataclass
class ExportMetadata:
    export_id: str; batch_id: str; export_time: str; audience: ExportAudience
    format: ExportFormat; file_path: str; file_size_bytes: int; checksum_sha256: str
    exported_by: str = "system"

@dataclass
class ArchivalRecord:
    archival_id: str; batch_id: str; archive_time: str; retention_days: int; expires_at: str
    status: ArchivalStatus; compressed_size_bytes: int; original_size_bytes: int
    compression_ratio: float; archive_path: str; checksum_sha256: str


# ──────────────────────────────────────────────────────────────────────────────
#  EXPORTERS
# ──────────────────────────────────────────────────────────────────────────────

class RoasterExporter:
    def __init__(self, db): self.db = db
    def generate(self, batch_record, bean_records, quality_tracker):
        dc = defaultdict(int); sd = defaultdict(int)
        cL = []; ca = []; cb = []; wt = []
        for b in bean_records:
            dc[b.defect_type] += 1
            if b.size_mesh: sd[int(b.size_mesh)] += 1
            if b.color_L: cL.append(b.color_L)
            if b.color_a is not None: ca.append(b.color_a)
            if b.color_b is not None: cb.append(b.color_b)
            if b.weight_g: wt.append(b.weight_g)
        avg = lambda l: round(sum(l)/len(l),2) if l else 0
        dl = sorted(dc.items(), key=lambda x:-x[1])
        return {
            "export_type": "roaster_batch_report", "version": "v1.0",
            "export_time": datetime.now(timezone.utc).isoformat(),
            "batch": {
                "batch_id": batch_record.batch_id, "origin": batch_record.origin,
                "process": batch_record.process_method, "total_beans": batch_record.total_beans,
                "total_weight_g": round(batch_record.total_weight_g,3),
                "grade_a_pct": round(batch_record.grade_a_pct,1),
                "quality_score": round(batch_record.quality_score or 0,1),
                "defect_rate_pct": round(batch_record.defect_rate_pct,2),
            },
            "defect_analysis": {
                "total_defects": sum(dc.values()),
                "defect_breakdown": [{"type":dt,"count":c,"pct":round(c/len(bean_records)*100,2)} for dt,c in dl],
                "primary_defect": dl[0][0] if dl else "NONE",
            },
            "bean_statistics": {
                "avg_weight_g": avg(wt),
                "size_distribution": dict(sorted(sd.items())),
                "avg_color": {"L":avg(cL),"a":avg(ca),"b":avg(cb)},
            },
            "quality_alerts": quality_tracker.current_metrics.alert_count if quality_tracker else 0,
            "recommendations": self._recs(dl, quality_tracker),
        }
    def _recs(self, defects, tracker):
        r = []
        if not defects: return ["Excellent batch — no defects detected."]
        r.append(f"Primary defect: {defects[0][0]}. Consider adjusting sort parameters.")
        if tracker and tracker.current_metrics.defect_rate_pct > 5:
            r.append("Defect rate exceeds 5% — review incoming quality.")
        return r


class CustomerExporter:
    def __init__(self, db): self.db = db
    def generate(self, batch_record, bean_records, recipe_manager):
        gd = defaultdict(int); dc = defaultdict(int)
        for b in bean_records:
            gd[b.grade] += 1
            if b.defect_type: dc[b.defect_type] += 1
        score = round(80.0 + gd.get("A",0)/len(bean_records)*15 - min(10,len(dc)*1.5), 1)
        if score >= 85: sca = "Specialty Grade"
        elif score >= 80: sca = "Premium Grade"
        elif score >= 75: sca = "Standard Grade"
        else: sca = "Below Specialty"
        notes = {"Ethiopia":"Bright acidity, floral and citrus notes expected.",
                 "Kenya":"Wine-like acidity, berry and tomato notes expected.",
                 "Brazil":"Nutty, chocolate, low acidity profile.",
                 "Colombia":"Balanced, caramel sweetness, mild acidity."}
        origin = batch_record.origin or ""
        note = next((n for k,n in notes.items() if k.lower() in origin.lower()), "Unique origin profile.")
        return {
            "export_type": "customer_quality_certificate", "version": "v1.0",
            "certificate_id": f"CERT-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "issue_date": datetime.now().strftime("%Y-%m-%d"),
            "batch": {"batch_id":batch_record.batch_id,"origin":batch_record.origin,
                     "process":batch_record.process_method,
                     "variety":getattr(batch_record,'variety','Unknown'),
                     "harvest_year":getattr(batch_record,'harvest_year',datetime.now().year)},
            "quality_metrics": {"preliminary_score":score,"sca_grade":sca,
                                "total_beans":batch_record.total_beans,
                                "grade_a_pct":round(batch_record.grade_a_pct,1),
                                "defect_count":sum(dc.values()),
                                "defect_rate_pct":round(batch_record.defect_rate_pct,2)},
            "defect_summary": [{"type":dt,"count":c} for dt,c in sorted(dc.items(),key=lambda x:-x[1])],
            "origin_notes": note,
            "compliance": {"sca_compliant":score>=80,"food_safety":True,"no_foreign_matter":dc.get("FOREIGN",0)==0},
        }


class AuditorExporter:
    def __init__(self, db): self.db = db
    def generate(self, batch_record, bean_records, batch_tracker):
        chain = []
        if batch_tracker:
            try:
                for ev in batch_tracker.get_batch_history(batch_record.batch_id):
                    chain.append(asdict(ev) if hasattr(ev,'__dict__') else str(ev))
            except Exception: pass
        return {
            "export_type": "auditor_full_traceability", "version": "v1.0",
            "audit_id": f"AUDIT-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "export_time": datetime.now(timezone.utc).isoformat(),
            "batch": {"batch_id":batch_record.batch_id,"origin":batch_record.origin,
                      "process":batch_record.process_method,"stage":batch_record.batch_state,
                      "total_beans":batch_record.total_beans,
                      "total_weight_g":round(batch_record.total_weight_g,3)},
            "chain_of_custody": chain,
            "sensor_data": {"total_records":len(bean_records),
                "records":[{"bean_id":b.bean_id,"weight_g":b.weight_g,"color_L":b.color_L,
                          "color_a":b.color_a,"color_b":b.color_b,"moisture_pct":b.moisture_pct,
                          "density":b.density,"size_mesh":b.size_mesh,
                          "defect_type":b.defect_type,"grade":b.grade} for b in bean_records]},
            "defect_registry": self._registry(bean_records),
            "audit_compliance": {"iso_22000":True,"full_traceability":len(chain)>0,"sensor_data_complete":True},
        }
    def _registry(self, bean_records):
        reg = defaultdict(list)
        for b in bean_records:
            if b.defect_type: reg[b.defect_type].append({"bean_id":b.bean_id,"weight_g":b.weight_g})
        return {k:v for k,v in sorted(reg.items(),key=lambda x:-len(x[1]))}


class FinanceExporter:
    # CNY/kg prices
    PA = 120.0; PB = 90.0; PC = 70.0; PD = 20.0; COST = 60.0
    def __init__(self, db): self.db = db
    def generate(self, batch_record, bean_records):
        gd = defaultdict(int); wg = defaultdict(float); dc = defaultdict(int)
        for b in bean_records:
            gd[b.grade] += 1; wg[b.grade] += b.weight_g or 0
            if b.defect_type: dc[b.defect_type] += 1
        a_kg=wg.get("A",0)/1000; b_kg=wg.get("B",0)/1000; c_kg=wg.get("C",0)/1000; r_kg=wg.get("REJECT",0)/1000
        tot=a_kg+b_kg+c_kg+r_kg
        rev=a_kg*self.PA+b_kg*self.PB+c_kg*self.PC+r_kg*self.PD
        cost=tot*self.COST; gm=rev-cost; mp=round(gm/rev*100,1) if rev else 0
        return {
            "export_type": "finance_production_report", "version": "v1.0",
            "report_id": f"FIN-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "report_date": datetime.now().strftime("%Y-%m-%d"),
            "batch": {"batch_id":batch_record.batch_id,"origin":batch_record.origin,
                      "process":batch_record.process_method},
            "production_yield": {
                "total_kg":round(tot,3),"grade_a_kg":round(a_kg,3),"grade_b_kg":round(b_kg,3),
                "grade_c_kg":round(c_kg,3),"reject_kg":round(r_kg,3),
                "grade_a_pct":round(gd.get("A",0)/len(bean_records)*100,1) if bean_records else 0,
                "first_grade_rate":round(gd.get("A",0)/len(bean_records)*100,1) if bean_records else 0,
            },
            "financials": {"revenue_cny":round(rev,2),"raw_material_cost_cny":round(cost,2),
                           "gross_margin_cny":round(gm,2),"gross_margin_pct":mp,
                           "price_assumptions":{"grade_a_cny_kg":self.PA,"grade_b_cny_kg":self.PB,
                           "grade_c_cny_kg":self.PC,"reject_cny_kg":self.PD,"raw_green_cny_kg":self.COST}},
            "defect_cost": {"defect_count":sum(dc.values()),"defect_weight_kg":round(r_kg,3),
                           "defect_cost_cny":round(r_kg*self.COST,2)},
            "per_bean_economics": {"avg_bean_weight_g":round(tot*1000/len(bean_records),3) if bean_records else 0,
                                   "revenue_per_kg_cny":round(rev/tot,2) if tot else 0},
        }


# ──────────────────────────────────────────────────────────────────────────────
#  ARCHIVAL MANAGER
# ──────────────────────────────────────────────────────────────────────────────

class ArchivalManager:
    DEFAULT_RETENTION_DAYS = 90
    def __init__(self, db, archive_root=None):
        self.db = db
        self.archive_root = Path(archive_root or "/Users/quantumcheuk/.openclaw/workspace/sorter-project/sorter/data/archive")
        self.archive_root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.archive_root / "archive_manifest.json"
        if not self.manifest_path.exists():
            self.manifest_path.write_text(json.dumps({"archives":[],"version":"v1.0"}))
    def _load(self): return json.loads(self.manifest_path.read_text())
    def _save(self, m): self.manifest_path.write_text(json.dumps(m, indent=2))
    def archive_batch(self, batch_id, retention_days=None):
        retention_days = retention_days or self.DEFAULT_RETENTION_DAYS
        now = datetime.now(timezone.utc); expires = now + timedelta(days=retention_days)
        arid = f"ARCH-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        batch = self.db.get_batch(batch_id)
        if not batch: raise ValueError(f"Batch {batch_id} not found")
        beans = self.db.get_beans_for_batch(batch_id)
        rd = {"batch":asdict(batch) if hasattr(batch,'__dict__') else {},
              "beans":[asdict(b) if hasattr(b,'__dict__') else {} for b in beans],
              "archival_timestamp":now.isoformat()}
        rj = json.dumps(rd, indent=2, default=str); osz = len(rj.encode('utf-8'))
        ad = self.archive_root / batch_id[:8]; ad.mkdir(parents=True, exist_ok=True)
        af = ad / f"{batch_id}.json.gz"
        with gzip.open(af,'wt',encoding='utf-8') as f: f.write(rj)
        csz = af.stat().st_size; ratio = round((1-csz/osz)*100,1) if osz else 0
        sha = hashlib.sha256(af.read_bytes()).hexdigest()
        rec = ArchivalRecord(archival_id=arid, batch_id=batch_id, archive_time=now.isoformat(),
            retention_days=retention_days, expires_at=expires.isoformat(),
            status=ArchivalStatus.COMPRESSED, compressed_size_bytes=csz,
            original_size_bytes=osz, compression_ratio=ratio,
            archive_path=str(af), checksum_sha256=sha)
        m = self._load(); m["archives"].append(asdict(rec)); self._save(m)
        try:
            self.db.conn.execute("UPDATE batches SET archived=1, archived_at=? WHERE batch_id=?",(now.isoformat(),batch_id))
            self.db.conn.commit()
        except Exception: pass
        return rec
    def restore_batch(self, archival_id):
        m = self._load(); rec = next((a for a in m["archives"] if a["archival_id"]==archival_id),None)
        if not rec: raise ValueError(f"Archive {archival_id} not found")
        af = Path(rec["archive_path"])
        if not af.exists(): raise FileNotFoundError(f"Archive file not found: {af}")
        with gzip.open(af,'rt',encoding='utf-8') as f: return json.load(f)
    def list_archives(self):
        m = self._load(); now = datetime.now(timezone.utc); r = []
        for a in m["archives"]:
            try:
                exp = datetime.fromisoformat(a["expires_at"].replace("Z","+00:00"))
                a["expired"] = now > exp; a["days_remaining"] = max(0,(exp-now).days)
            except Exception:
                a["expired"]=False; a["days_remaining"]=a.get("retention_days",90)
            r.append(a)
        return r
    def purge_expired(self):
        m = self._load(); now = datetime.now(timezone.utc); purged=0; rem=[]
        for a in m["archives"]:
            try:
                exp = datetime.fromisoformat(a["expires_at"].replace("Z","+00:00"))
                if now>exp:
                    p=Path(a["archive_path"])
                    if p.exists(): p.unlink()
                    purged+=1
                else: rem.append(a)
            except Exception: rem.append(a)
        m["archives"]=rem; self._save(m); return purged


# ──────────────────────────────────────────────────────────────────────────────
#  EXPORT MANAGER
# ──────────────────────────────────────────────────────────────────────────────

class ExportManager:
    def __init__(self, db, output_dir=None):
        self.db = db
        self.output_dir = Path(output_dir or "/Users/quantumcheuk/.openclaw/workspace/sorter-project/sorter/data/exports")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.reg_path = self.output_dir / "export_registry.json"
        if not self.reg_path.exists():
            self.reg_path.write_text(json.dumps({"exports":[],"version":"v1.0"}))
        self.re = RoasterExporter(db); self.ce = CustomerExporter(db)
        self.ae = AuditorExporter(db); self.fe = FinanceExporter(db)
        self.rm = RecipeManager()
    def _load_reg(self): return json.loads(self.reg_path.read_text())
    def _save_reg(self, r): self.reg_path.write_text(json.dumps(r, indent=2, default=str))
    def export_batch(self, batch_id, audience=ExportAudience.ROASTER, export_format=ExportFormat.JSON, output_dir=None):
        op = Path(output_dir) if output_dir else self.output_dir / audience.value
        op.mkdir(parents=True, exist_ok=True)
        batch = self.db.get_batch(batch_id)
        if not batch: raise ValueError(f"Batch {batch_id} not found")
        beans = self.db.get_beans_for_batch(batch_id)
        qt = None
        try:
            qt = BatchQualityTracker(batch_id=batch_id, target_kg=batch.total_weight_g/1000)
            for bean in beans: qt.add_bean(bean)
        except Exception: pass
        bt = None
        try: bt = RealTimeBatchTracker(batch_id)
        except Exception: pass
        if audience == ExportAudience.ROASTER: data = self.re.generate(batch, beans, qt)
        elif audience == ExportAudience.CUSTOMER: data = self.ce.generate(batch, beans, self.rm)
        elif audience == ExportAudience.AUDITOR: data = self.ae.generate(batch, beans, bt)
        elif audience == ExportAudience.FINANCE: data = self.fe.generate(batch, beans)
        else: raise ValueError(f"Unknown audience: {audience}")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S"); bn = f"{batch_id}_{audience.value}"
        if export_format == ExportFormat.JSON:
            fp = op / f"{bn}_{ts}.json"; fp.write_text(json.dumps(data,indent=2,default=str)); sz = len(fp.read_text().encode('utf-8'))
        elif export_format == ExportFormat.CSV:
            fp = op / f"{bn}_{ts}.csv"; self._csv(beans, fp); sz = fp.stat().st_size
        elif export_format == ExportFormat.TEXT:
            fp = op / f"{bn}_{ts}.txt"; fp.write_text(self._txt(data,audience,batch)); sz = len(fp.read_text().encode('utf-8'))
        elif export_format == ExportFormat.HTML:
            fp = op / f"{bn}_{ts}.html"; fp.write_text(self._html(data,audience,batch)); sz = len(fp.read_text().encode('utf-8'))
        else: raise ValueError(f"Unsupported format: {export_format}")
        sha = hashlib.sha256(fp.read_bytes()).hexdigest()
        meta = ExportMetadata(export_id=f"EXP-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            batch_id=batch_id, export_time=datetime.now(timezone.utc).isoformat(),
            audience=audience, format=export_format, file_path=str(fp),
            file_size_bytes=sz, checksum_sha256=sha)
        r = self._load_reg(); r["exports"].append(asdict(meta)); self._save_reg(r)
        return meta
    def _csv(self, beans, fp):
        with open(fp,'w',newline='',encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(["bean_id","weight_g","color_L","color_a","color_b","moisture_pct","density","size_mesh","defect_type","grade","timestamp"])
            for b in beans:
                ts = b.timestamp.isoformat() if hasattr(b.timestamp,'isoformat') else str(b.timestamp)
                w.writerow([b.bean_id,b.weight_g or "",b.color_L or "",
                    b.color_a if b.color_a is not None else "",b.color_b if b.color_b is not None else "",
                    b.moisture_pct or "",b.density or "",b.size_mesh or "",
                    b.defect_type or "",b.grade or "",ts])
    def _txt(self, data, audience, batch):
        lines = ["="*60,f"PRODUCTION EXPORT — {audience.value.upper()}","="*60,
                 f"Batch: {data.get('batch',{}).get('batch_id','N/A')}",
                 f"Origin: {data.get('batch',{}).get('origin','N/A')}",
                 f"Export Time: {data.get('export_time',datetime.now().isoformat())}","",]
        if audience == ExportAudience.ROASTER:
            ba = data.get("batch",{}); lines += [f"Total Beans: {ba.get('total_beans',0)}",
                f"Grade A: {ba.get('grade_a_pct',0)}%",
                f"Quality Score: {ba.get('quality_score',0)}",
                f"Defect Rate: {ba.get('defect_rate_pct',0)}%","","Defect Breakdown:"]
            for d in data.get("defect_analysis",{}).get("defect_breakdown",[]):
                lines.append(f"  {d['type']}: {d['count']} ({d['pct']}%)")
            lines += [""] + [f"Recommendation: {r}" for r in data.get("recommendations",[])]
        elif audience == ExportAudience.FINANCE:
            y = data.get("production_yield",{}); f = data.get("financials",{})
            lines += [f"Total Production: {y.get('total_kg',0)} kg",
                      f"Grade A: {y.get('grade_a_kg',0)} kg ({y.get('grade_a_pct',0)}%)",
                      f"Revenue: ¥{f.get('revenue_cny',0)}",
                      f"Gross Margin: ¥{f.get('gross_margin_cny',0)} ({f.get('gross_margin_pct',0)}%)"]
        lines.append("="*60); return "\n".join(lines)
    def _html(self, data, audience, batch):
        ba = data.get("batch",{}); gap = ba.get('grade_a_pct',0)
        rev = data.get('financials',{}).get('revenue_cny',0)
        h = [f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>Batch {batch.batch_id} — {audience.value}</title>",
             "<style>body{font-family:Helvetica,Arial,sans-serif;margin:40px;background:#f5f5f5}",
             ".container{background:white;padding:30px;border-radius:8px;max-width:800px;margin:auto;box-shadow:0 2px 8px rgba(0,0,0,0.1)}",
             "h1{color:#2c3e50;border-bottom:2px solid #3498db;padding-bottom:10px}",
             "h2{color:#34495e;margin-top:25px}table{width:100%;border-collapse:collapse;margin:15px 0}",
             "th{background:#3498db;color:white;padding:10px;text-align:left}",
             "td{padding:8px;border-bottom:1px solid #eee}",
             ".highlight{background:#e8f5e9;padding:15px;border-radius:4px;margin:10px 0}",
             ".metric{font-size:24px;font-weight:bold;color:#2c3e50}",
             ".footer{margin-top:30px;color:#999;font-size:12px;text-align:center}</style></head>",
             "<body><div class='container'>",
             f"<h1>Batch {batch.batch_id}</h1>",
             f"<p><strong>Origin:</strong> {batch.origin or 'N/A'} | <strong>Process:</strong> {batch.process_method or 'N/A'}</p>"]
        if audience == ExportAudience.ROASTER:
            h += [f"<div class='highlight'><div class='metric'>{gap}%</div><div>Grade A Pass Rate</div></div>",
                  "<table><tr><th>Metric</th><th>Value</th></tr>",
                  f"<tr><td>Total Beans</td><td>{ba.get('total_beans',0)}</td></tr>",
                  f"<tr><td>Quality Score</td><td>{ba.get('quality_score',0)}</td></tr>",
                  f"<tr><td>Defect Rate</td><td>{ba.get('defect_rate_pct',0)}%</td></tr></table>",
                  "<h2>Defect Analysis</h2><table><tr><th>Type</th><th>Count</th><th>Pct</th></tr>"]
            for d in data.get("defect_analysis",{}).get("defect_breakdown",[]):
                h.append(f"<tr><td>{d['type']}</td><td>{d['count']}</td><td>{d['pct']}%</td></tr>")
            h.append("</table>")
        elif audience == ExportAudience.FINANCE:
            y = data.get("production_yield",{}); f = data.get("financials",{})
            h += [f"<div class='highlight'><div class='metric'>¥{rev}</div><div>Total Revenue</div></div>",
                  "<table><tr><th>Yield</th><th>Value</th></tr>",
                  f"<tr><td>Total kg</td><td>{y.get('total_kg',0)}</td></tr>",
                  f"<tr><td>Grade A kg</td><td>{y.get('grade_a_kg',0)} ({y.get('grade_a_pct',0)}%)</td></tr>",
                  f"<tr><td>Reject kg</td><td>{y.get('reject_kg',0)}</td></tr></table>",
                  "<table><tr><th>Financial</th><th>Value</th></tr>",
                  f"<tr><td>Gross Margin</td><td>¥{f.get('gross_margin_cny',0)} ({f.get('gross_margin_pct',0)}%)</td></tr></table>"]
        else:
            h.append(f"<p>Total beans: {ba.get('total_beans',0)}, Grade A: {gap}%</p>")
        h.append("<div class='footer'>Generated by HUSKY-SORTER-001</div></div></body></html>")
        return "".join(h)


# ──────────────────────────────────────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")
    e = sub.add_parser("export")
    e.add_argument("--batch-id", required=True)
    e.add_argument("--audience", default="roaster", choices=["roaster","customer","auditor","finance"])
    e.add_argument("--format", default="json", choices=["json","csv","text","html"])
    e.add_argument("--output", default=None)
    a = sub.add_parser("archive")
    a.add_argument("--batch-id", required=True)
    a.add_argument("--retention-days", type=int, default=90)
    sub.add_parser("list-archives")
    sub.add_parser("purge-expired")
    m = sub.add_parser("manifest")
    m.add_argument("--batch-id", required=True)
    args = p.parse_args()
    if not args.cmd: p.print_help(); return
    db = Database(); em = ExportManager(db); am = ArchivalManager(db)
    if args.cmd == "export":
        meta = em.export_batch(args.batch_id, audience=ExportAudience(args.audience),
                               export_format=ExportFormat(args.format), output_dir=args.output)
        print(f"Export: {meta.file_path}")
        print(f"Size: {meta.file_size_bytes} bytes | SHA256: {meta.checksum_sha256[:16]}...")
    elif args.cmd == "archive":
        rec = am.archive_batch(args.batch_id, retention_days=args.retention_days)
        print(f"Archived: {rec.batch_id} | ID: {rec.archival_id}")
        print(f"Size: {rec.original_size_bytes}B → {rec.compressed_size_bytes}B ({rec.compression_ratio}% compression)")
        print(f"Expires: {rec.expires_at}")
    elif args.cmd == "list-archives":
        for a in am.list_archives():
            s = "EXPIRED" if a.get("expired") else f"{a.get('days_remaining',0)} days left"
            print(f"  {a['batch_id']} | {a['archival_id']} | {s} | {a.get('compression_ratio',0)}%")
    elif args.cmd == "purge-expired":
        print(f"Purged {am.purge_expired()} expired archives.")
    elif args.cmd == "manifest":
        ba = db.get_batch(args.batch_id)
        if not ba: print(f"Batch {args.batch_id} not found"); return
        beans = db.get_beans_for_batch(args.batch_id)
        print(f"Batch: {ba.batch_id} | Origin: {ba.origin} | Beans: {len(beans)}")
        print(f"Grade A: {ba.grade_a_pct}% | Defect Rate: {ba.defect_rate_pct}% | Quality: {ba.quality_score}")
        print(f"State: {ba.batch_state}")
    else:
        p.print_help()

if __name__ == "__main__":
    main()
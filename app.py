import streamlit as st
import pandas as pd
import openpyxl
import io
import copy
import math

st.set_page_config(page_title="Simulador Costes Obra", page_icon="🏗️", layout="wide", initial_sidebar_state="expanded")

# ═══════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════
HHEE_POR_DIA_PERSONA = 2.5

CHAPTER_DEFS = [
    {"key": "personal",    "label": "PERSONAL",            "start": 21, "end": 35,  "sub": 51, "driver": "tiempo"},
    {"key": "armadura",    "label": "ARMADURA",            "start": 53, "end": 66,  "sub": 67, "driver": "medicion"},
    {"key": "cemento",     "label": "CEMENTO",             "start": 69, "end": 73,  "sub": 74, "driver": "medicion"},
    {"key": "materiales",  "label": "OTROS MATERIALES",    "start": 76, "end": 90,  "sub": 91, "driver": "medicion"},
    {"key": "subcontrata", "label": "SUBCONTRATA",         "start": 95, "end": 107, "sub": 108, "driver": "medicion"},
    {"key": "maq_externa", "label": "MAQUINARIA EXTERNA",  "start": 109, "end": 115, "sub": 116, "driver": "tiempo"},
    {"key": "otros_alq",   "label": "OTROS ALQUILERES",    "start": 125, "end": 133, "sub": 134, "driver": "tiempo"},
    {"key": "consumibles", "label": "CONSUMIBLES / PARQUE","start": 137, "end": 152, "sub": 154, "driver": "medicion"},
    {"key": "gastos_var",  "label": "GASTOS VARIOS",       "start": 156, "end": 167, "sub": 168, "driver": "pct_prod"},
    {"key": "gasoil",      "label": "GASOIL",              "start": 172, "end": 173, "sub": 174, "driver": "tiempo_maq"},
    {"key": "transportes", "label": "TRANSPORTES",         "start": 176, "end": 177, "sub": 178, "driver": "pa"},
    {"key": "maq_interna", "label": "MAQUINARIA INTERNA",  "start": 180, "end": 181, "sub": 182, "driver": "tiempo_maq"},
]

PROD_RANGE = {"start": 188, "end": 210}

DRIVER_LABELS = {
    "tiempo": "⏱ Tiempo", "tiempo_maq": "⏱×🔧 T×Máq",
    "medicion": "📏 Medición", "pa": "📦 P.A.", "pct_prod": "📊 %Prod",
}

PERSONAL_POR_MAQ = {"jefe": 0, "encargado": 0, "oficial 1": 1, "oficial 2": 1, "ayudante": 2.5, "peon": 2.5}
PERSONAL_GENERA_HHEE = {"jefe": False, "encargado": True, "oficial 1": True, "oficial 2": True, "ayudante": True, "peon": True, "horas": False}

def ceil1(n): return math.ceil(n * 10) / 10
def fmt_eur(n):
    if n is None: return "—"
    return f"{round(n):,} €".replace(",", ".")
def fmt_n(n):
    if n is None: return "—"
    return f"{ceil1(n):,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
def desv_str(val):
    if abs(val) < 1: return "—"
    return f"{'+' if val > 0 else ''}{round(val):,} €".replace(",", ".")

def get_personal_key(nombre):
    n = nombre.lower()
    for k in ["jefe", "encargado"]: 
        if k in n: return k
    if "oficial 1" in n or "oficial 1" in n: return "oficial 1"
    if "oficial 2" in n or "oficial 2" in n: return "oficial 2"
    if any(x in n for x in ["ayudante", "peon", "peón"]): return "peon"
    if "hora" in n and "extra" in n: return "horas"
    return None

def infer_driver(nombre, med, pu, chapter_driver, base_dias_adj, base_ml, prod_total):
    if med and prod_total and abs(med - prod_total) < 1000 and pu and pu < 0.1:
        return "pct_prod"
    if pu == 1 and med and med > 100:
        return "pa"
    return chapter_driver

# ═══════════════════════════════════════════════════════════════════
# PARSER
# ═══════════════════════════════════════════════════════════════════
@st.cache_data
def parse_excel(file_bytes):
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
    sheet_name = next((n for n in wb.sheetnames if n.upper() in ("COSTOS","COSTES","COSTS")), wb.sheetnames[0])
    ws = wb[sheet_name]
    
    all_rows = {}
    for row in ws.iter_rows(min_row=1, max_row=220, min_col=1, max_col=18, values_only=False):
        rn = None
        for c in row:
            if hasattr(c, 'row') and c.row: rn = c.row; break
        if rn is None: continue
        all_rows[rn] = {k: row[i].value for i, k in enumerate(["A","B","C","D","E","F","G","H","I"]) if i < len(row)}
    wb.close()
    
    params = {
        "nombre_obra": str(all_rows.get(3,{}).get("D","") or "").strip(),
        "expediente": str(all_rows.get(2,{}).get("D","") or "").strip(),
        "num_equipos": int(all_rows.get(8,{}).get("C",2) or 2),
        "total_ml": float(all_rows.get(9,{}).get("C",0) or 0),
        "rendimiento": float(all_rows.get(10,{}).get("C",0) or 0),
    }
    
    prod_total = sum(
        (all_rows.get(rn,{}).get("H",0) or 0) * (all_rows.get(rn,{}).get("G",0) or 0)
        for rn in range(PROD_RANGE["start"], PROD_RANGE["end"]+1)
        if isinstance(all_rows.get(rn,{}).get("H"), (int,float)) and isinstance(all_rows.get(rn,{}).get("G"), (int,float))
    )
    
    base_dias_adj = 24
    for rn in range(21, 35):
        g = all_rows.get(rn,{}).get("G")
        if g and isinstance(g,(int,float)) and g > 0: base_dias_adj = g; break
    
    chapters = []
    for cdef in CHAPTER_DEFS:
        items = []
        for rn in range(cdef["start"], cdef["end"]+1):
            r = all_rows.get(rn, {})
            b,h,g,i_val = r.get("B"), r.get("H"), r.get("G"), r.get("I")
            
            if h is not None and g is not None and isinstance(h,(int,float)) and isinstance(g,(int,float)) and h*g != 0:
                nombre = str(b or "").strip()
                driver = infer_driver(nombre, g, h, cdef["driver"], base_dias_adj, params["total_ml"], prod_total)
                personas, ppm, gen_hhee, es_hhee = None, None, False, False
                if cdef["key"] == "personal":
                    pkey = get_personal_key(nombre)
                    if pkey == "horas": es_hhee = True
                    elif pkey and base_dias_adj > 0:
                        personas = round(g / base_dias_adj)
                        ppm = PERSONAL_POR_MAQ.get(pkey, 0)
                        gen_hhee = PERSONAL_GENERA_HHEE.get(pkey, False)
                items.append({"nombre": nombre or f"Línea {rn}", "pu": round(h,4), "med": round(g,4), "total": round(h*g,2), "driver": driver, "personas": personas, "personas_por_maq": ppm, "genera_hhee": gen_hhee, "es_hhee": es_hhee})
            
            elif i_val and isinstance(i_val,(int,float)) and i_val != 0:
                nombre = str(b or "").strip()
                if nombre and nombre.lower() not in ("","libre","local","ejemplo cem"):
                    if not any(rn == cd["sub"] for cd in CHAPTER_DEFS):
                        items.append({"nombre": nombre, "pu": 1, "med": round(i_val,2), "total": round(i_val,2), "driver": "pa", "personas": None, "personas_por_maq": None, "genera_hhee": False, "es_hhee": False})
        
        sr = all_rows.get(cdef["sub"],{})
        subtotal = sr.get("I",0)
        if not isinstance(subtotal,(int,float)): subtotal = sum(it["total"] for it in items)
        if not items and isinstance(subtotal,(int,float)) and subtotal > 0:
            items.append({"nombre": str(sr.get("B",cdef["label"]) or cdef["label"]).strip(), "pu": 1, "med": round(subtotal,2), "total": round(subtotal,2), "driver": cdef["driver"], "personas": None, "personas_por_maq": None, "genera_hhee": False, "es_hhee": False})
        chapters.append({"key": cdef["key"], "label": cdef["label"], "items": items, "subtotal": round(subtotal,2), "driver_default": cdef["driver"]})
    
    prod_items = []
    for rn in range(PROD_RANGE["start"], PROD_RANGE["end"]+1):
        r = all_rows.get(rn,{})
        b,h,g = r.get("B"), r.get("H"), r.get("G")
        if h and g and isinstance(h,(int,float)) and isinstance(g,(int,float)) and h*g != 0:
            nombre = str(b or "").strip()
            if nombre.lower() != "excesos":
                prod_items.append({"nombre": nombre, "pu": round(h,4), "med": round(g,4), "total": round(h*g,2)})
    
    return {"params": params, "chapters": chapters, "production": prod_items, "base_dias_adj": base_dias_adj, "prod_total": round(prod_total,2)}

# ═══════════════════════════════════════════════════════════════════
# SIMULATION
# ═══════════════════════════════════════════════════════════════════
def simulate(data, sp, sim_ch, sim_prod):
    ba = data["base_dias_adj"]
    bm = data["params"]["num_equipos"]
    rt = sp["rendimiento"] * sp["num_maquinas"]
    dt = sp["total_ml"] / rt if rt > 0 else 0
    da = dt + sp["dias_extra"]
    fd = da / ba if ba > 0 else 1
    fm = sp["total_ml"] / data["params"]["total_ml"] if data["params"]["total_ml"] > 0 else 1
    fmaq = sp["num_maquinas"] / bm if bm > 0 else 1
    tp = sum(p["pu"]*p["med"] for p in sim_prod)
    
    res_ch = []; tc = 0
    for ci, ch in enumerate(sim_ch):
        items = []
        for ii, it in enumerate(ch["items"]):
            mc = it["med"]; ap = it.get("personas"); mb = it.get("med_base", it["med"]); dr = it["driver"]
            if dr == "tiempo":
                if it.get("es_hhee"): mc = 0
                elif it.get("personas") is not None:
                    ap = it["personas"]
                    if not it.get("_pm"):
                        ppm = it.get("personas_por_maq")
                        if ppm is not None and ppm > 0: ap = ppm * sp["num_maquinas"]
                        elif ppm == 0:
                            oi = data["chapters"][ci]["items"][ii] if ii < len(data["chapters"][ci]["items"]) else None
                            if oi: ap = oi.get("personas", it["personas"])
                    mc = ap * da
                else: mc = mb * fd
            elif dr == "tiempo_maq": mc = mb * fd * fmaq
            elif dr == "medicion": mc = mb * fm
            elif dr == "pct_prod": mc = tp
            t = it["pu"] * mc
            items.append({**it, "med_calc": round(mc,2), "total_sim": round(t,2), "_ap": ap})
        
        if ch["key"] == "personal":
            ph = sum((i.get("_ap") or 0) for i in items if i.get("genera_hhee"))
            for i, it in enumerate(items):
                if it.get("es_hhee"):
                    mc = HHEE_POR_DIA_PERSONA * ph * da
                    items[i] = {**it, "med_calc": round(mc,2), "total_sim": round(it["pu"]*mc,2)}
        
        ct = sum(i["total_sim"] for i in items); tc += ct
        res_ch.append({**ch, "items": items, "total_sim": round(ct,2)})
    
    mg = tp - tc
    return {"dt": round(dt,2), "da": round(da,2), "rt": round(rt,2), "tp": round(tp,2), "tc": round(tc,2), "mg": round(mg,2), "mb": mg/tp if tp > 0 else 0, "chapters": res_ch}

# ═══════════════════════════════════════════════════════════════════
# UI
# ═══════════════════════════════════════════════════════════════════
def main():
    st.markdown("<style>.block-container{padding:1rem 2rem;} div[data-testid='stMetricValue']{font-size:1.6rem;}</style>", unsafe_allow_html=True)
    st.title("🏗️ Simulador de Presupuesto de Obra")
    
    uploaded = st.file_uploader("Sube el fichero .xlsm de costes", type=["xlsm","xlsx"])
    if not uploaded: st.info("👆 Sube un fichero Excel de costes para comenzar."); st.stop()
    
    data = parse_excel(uploaded.read())
    p = data["params"]
    st.caption(f"**{p['nombre_obra']}** · Exp. {p['expediente']} · {p['total_ml']} ML · {p['num_equipos']} equipos")
    
    # Sidebar
    st.sidebar.header("⚙️ Parámetros")
    sml = st.sidebar.number_input("ML Totales", value=float(p["total_ml"]), step=10.0, format="%.1f")
    srn = st.sidebar.number_input("Rendimiento ML/día/máq", value=float(p["rendimiento"]), step=1.0, format="%.2f")
    smq = st.sidebar.number_input("Nº Máquinas", value=int(p["num_equipos"]), min_value=1, step=1)
    bde = round(data["base_dias_adj"] - (p["total_ml"]/(p["rendimiento"]*p["num_equipos"])) if p["rendimiento"]*p["num_equipos"] > 0 else 4, 1)
    sde = st.sidebar.number_input("Días extra (montaje/avería)", value=float(bde), step=0.5, format="%.1f")
    
    rt = srn*smq; dtt = sml/rt if rt > 0 else 0; daa = dtt+sde
    st.sidebar.markdown(f"---\n**Rend. total:** {rt:.1f} ML/d · **Días teór:** {dtt:.1f} · **Días ajust:** {daa:.1f}")
    sp = {"total_ml": sml, "rendimiento": srn, "num_maquinas": smq, "dias_extra": sde}
    
    # State
    if "sc" not in st.session_state or st.sidebar.button("🔄 Reset"):
        sc = []
        for ch in data["chapters"]:
            items = [{**it, "med_base": it["med"]} for it in ch["items"]]
            for j in range(2): items.append({"nombre":"","pu":0,"med":0,"med_base":0,"total":0,"driver":"pa","personas":None,"personas_por_maq":None,"genera_hhee":False,"es_hhee":False,"_extra":True})
            sc.append({**ch, "items": items})
        st.session_state.sc = sc
        sp2 = copy.deepcopy(data["production"])
        for j in range(2): sp2.append({"nombre":"","pu":0,"med":0,"total":0,"_extra":True})
        st.session_state.sp = sp2
    
    R = simulate(data, sp, st.session_state.sc, st.session_state.sp)
    oc = sum(ch["subtotal"] for ch in data["chapters"]); op = data["prod_total"]; om = op-oc; opc = om/op if op > 0 else 0
    dmb = R["mb"] - opc
    
    # KPIs
    k1,k2,k3,k4 = st.columns(4)
    with k1: st.metric("% MB", f"{R['mb']*100:.2f}%", f"{dmb*100:+.2f}pp")
    with k2: st.metric("Margen Bruto", fmt_eur(R["mg"]), desv_str(R["mg"]-om))
    with k3: st.metric("Coste Directo", fmt_eur(R["tc"]), desv_str(R["tc"]-oc), delta_color="inverse")
    with k4: st.metric("Producción", fmt_eur(R["tp"]), f"{smq} máq · {rt:.0f} ML/d · {daa:.1f} d")
    
    # Tabs
    tc_tab, tp_tab, tr_tab = st.tabs(["📊 Costes","💰 Producción","📋 Resumen"])
    
    with tc_tab:
        st.caption("Izquierda = Original │ Derecha = Simulado (editable) │ ⏱Tiempo ⏱×🔧T×Máq 📏Medición 📦PA 📊%Prod")
        for ci, chs in enumerate(R["chapters"]):
            cho = data["chapters"][ci]; dv = chs["total_sim"]-cho["subtotal"]; dvp = dv/cho["subtotal"]*100 if cho["subtotal"] > 0 else 0
            with st.expander(f"**{chs['label']}** — Orig: {fmt_eur(cho['subtotal'])} → Sim: {fmt_eur(chs['total_sim'])} ({dvp:+.1f}%)", expanded=False):
                rows = []
                for ii, si in enumerate(chs["items"]):
                    oi = cho["items"][ii] if ii < len(cho["items"]) else None; ie = si.get("_extra",False)
                    ot = oi["total"] if oi else 0; d = si["total_sim"]-ot
                    op2, sp2 = "", ""
                    if chs["key"]=="personal" and not si.get("es_hhee"):
                        if oi and oi.get("personas"): op2=str(oi["personas"])
                        ap=si.get("_ap"); 
                        if ap is not None: sp2=f"{ceil1(ap):.1f}"
                    r = {"Concepto": si["nombre"] or "(nuevo)", "Driver": DRIVER_LABELS.get(si["driver"],"") if not ie else "+"}
                    if chs["key"]=="personal": r["P orig"]=op2; r["P sim"]=sp2
                    r.update({"PU orig": fmt_n(oi["pu"]) if oi else "", "Med orig": fmt_n(oi["med"]) if oi else "", "Total orig": fmt_eur(ot) if oi else "", "│":"│", "PU sim": fmt_n(si["pu"]), "Med sim": fmt_n(si["med_calc"]), "Total sim": fmt_eur(si["total_sim"]), "Desv.": desv_str(d)})
                    rows.append(r)
                rows.append({"Concepto": f"TOTAL {chs['label']}", "Driver":"", **({k:"" for k in (["P orig","P sim"] if chs["key"]=="personal" else [])}), "PU orig":"","Med orig":"","Total orig": fmt_eur(cho["subtotal"]), "│":"│","PU sim":"","Med sim":"","Total sim": fmt_eur(chs["total_sim"]), "Desv.": desv_str(dv)})
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                
                st.markdown("##### ✏️ Editar")
                for ii in range(len(chs["items"])):
                    si = st.session_state.sc[ci]["items"][ii]; ie = si.get("_extra",False)
                    if ie:
                        c = st.columns([3,1,1])
                        with c[0]:
                            v = st.text_input("n",value=si["nombre"],key=f"n{ci}{ii}",label_visibility="collapsed",placeholder="Nuevo concepto...")
                            if v != si["nombre"]: st.session_state.sc[ci]["items"][ii]["nombre"]=v; st.rerun()
                        with c[1]:
                            v = st.number_input("p",value=float(si["pu"]),step=0.1,format="%.2f",key=f"p{ci}{ii}",label_visibility="collapsed")
                            if abs(v-si["pu"])>0.001: st.session_state.sc[ci]["items"][ii]["pu"]=v; st.rerun()
                        with c[2]:
                            v = st.number_input("m",value=float(si["med"]),step=1.0,format="%.1f",key=f"m{ci}{ii}",label_visibility="collapsed")
                            if abs(v-si["med"])>0.01: st.session_state.sc[ci]["items"][ii]["med"]=v; st.session_state.sc[ci]["items"][ii]["med_base"]=v; st.rerun()
                    else:
                        has_p = chs["key"]=="personal" and si.get("personas") is not None and not si.get("es_hhee")
                        nc = 4 if has_p else 3; c = st.columns([3]+[1]*(nc-1)); ci2=1
                        with c[0]: st.text(si["nombre"])
                        if has_p:
                            with c[ci2]:
                                ap = chs["items"][ii].get("_ap", si["personas"])
                                v = st.number_input("P",value=float(ap or 0),step=1.0,format="%.1f",key=f"pe{ci}{ii}",label_visibility="collapsed")
                                if abs(v-(ap or 0))>0.01: st.session_state.sc[ci]["items"][ii]["personas"]=v; st.session_state.sc[ci]["items"][ii]["_pm"]=True; st.rerun()
                            ci2+=1
                        with c[ci2]:
                            v = st.number_input("PU",value=float(si["pu"]),step=0.1,format="%.4f",key=f"p{ci}{ii}",label_visibility="collapsed")
                            if abs(v-si["pu"])>0.0001: st.session_state.sc[ci]["items"][ii]["pu"]=v; st.rerun()
                        with c[ci2+1]:
                            if si["driver"]=="pa" or ie:
                                v = st.number_input("M",value=float(si["med"]),step=1.0,format="%.1f",key=f"m{ci}{ii}",label_visibility="collapsed")
                                if abs(v-si["med"])>0.01: st.session_state.sc[ci]["items"][ii]["med"]=v; st.session_state.sc[ci]["items"][ii]["med_base"]=v; st.rerun()
                            else: st.text(f"{fmt_n(chs['items'][ii]['med_calc'])} (auto)")
        
        st.markdown("---")
        c1,c2,c3 = st.columns(3)
        with c1: st.metric("COSTE DIRECTO Original", fmt_eur(oc))
        with c2: st.metric("COSTE DIRECTO Simulado", fmt_eur(R["tc"]))
        with c3: st.metric("Desviación", desv_str(R["tc"]-oc))
    
    with tp_tab:
        rows = []
        for ii, s in enumerate(st.session_state.sp):
            o = data["production"][ii] if ii < len(data["production"]) else None; ie = s.get("_extra",False)
            ot = o["total"] if o else 0; st2 = s["pu"]*s["med"]; d = st2-ot
            rows.append({"Concepto": s["nombre"] or "(nuevo)", "PU orig": fmt_n(o["pu"]) if o else "", "Med orig": fmt_n(o["med"]) if o else "", "Total orig": fmt_eur(ot) if o else "", "│":"│", "PU sim": fmt_n(s["pu"]), "Med sim": fmt_n(s["med"]), "Total sim": fmt_eur(st2), "Desv.": desv_str(d)})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        
        st.markdown("##### ✏️ Editar")
        for ii, s in enumerate(st.session_state.sp):
            ie = s.get("_extra",False); c = st.columns([3,1,1])
            with c[0]:
                if ie:
                    v = st.text_input("n",value=s["nombre"],key=f"pn{ii}",label_visibility="collapsed",placeholder="Nuevo...")
                    if v != s["nombre"]: st.session_state.sp[ii]["nombre"]=v; st.rerun()
                else: st.text(s["nombre"])
            with c[1]:
                v = st.number_input("P",value=float(s["pu"]),step=0.1,format="%.2f",key=f"pp{ii}",label_visibility="collapsed")
                if abs(v-s["pu"])>0.001: st.session_state.sp[ii]["pu"]=v; st.rerun()
            with c[2]:
                v = st.number_input("M",value=float(s["med"]),step=1.0,format="%.1f",key=f"pm{ii}",label_visibility="collapsed")
                if abs(v-s["med"])>0.01: st.session_state.sp[ii]["med"]=v; st.rerun()
        
        st.markdown("---")
        c1,c2,c3 = st.columns(3)
        with c1: st.metric("Producción", fmt_eur(R["tp"]))
        with c2: st.metric("Coste Directo", fmt_eur(R["tc"]))
        with c3: st.metric("Margen Bruto", fmt_eur(R["mg"]), f"{R['mb']*100:.2f}%")
    
    with tr_tab:
        rows = []
        for ci, chs in enumerate(R["chapters"]):
            cho = data["chapters"][ci]; d = chs["total_sim"]-cho["subtotal"]; dp = d/cho["subtotal"]*100 if cho["subtotal"] > 0 else 0
            rows.append({"Capítulo": chs["label"], "Original": fmt_eur(cho["subtotal"]), "Simulado": fmt_eur(chs["total_sim"]), "Desviación": desv_str(d), "%": f"{dp:+.1f}%"})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.markdown("---")
        st.table(pd.DataFrame({"": ["COSTE DIRECTO","PRODUCCIÓN","MARGEN BRUTO","% MB"], "Original": [fmt_eur(oc),fmt_eur(op),fmt_eur(om),f"{opc*100:.2f}%"], "Simulado": [fmt_eur(R["tc"]),fmt_eur(R["tp"]),fmt_eur(R["mg"]),f"{R['mb']*100:.2f}%"], "Desviación": [desv_str(R["tc"]-oc),desv_str(R["tp"]-op),desv_str(R["mg"]-om),f"{dmb*100:+.2f}pp"]}))

if __name__ == "__main__":
    main()

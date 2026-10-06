let currentCarId=null,lightboxImages=[],lightboxIndex=0,userSettings={dashboard_range:'all',show_vehicles:true,show_records:true,show_cost:true,show_due:true,theme:'dark'};
const PERM_LABELS={can_add_cars:'Adicionar veículos',can_edit_cars:'Editar veículos',can_delete_cars:'Excluir veículos',can_add_records:'Adicionar registros',can_edit_records:'Editar registros',can_delete_records:'Excluir registros',can_import:'Importar CSV',can_export:'Exportar CSV'};

document.addEventListener('DOMContentLoaded',()=>{
    applyPermVisibility();populateUserMenu();
    document.getElementById('sidebarVersion').textContent='v'+APP_VERSION;
    loadSettings().then(()=>{applyTheme();loadDashboard();loadCars();loadSidebarCars()});
    if(CURRENT_USER.must_change_password)openModal('forceChangePwModal');
});

function applyPermVisibility(){
    document.querySelectorAll('.admin-only').forEach(el=>{el.style.display=CURRENT_USER.role==='admin'?'':'none'});
    Object.keys(PERM_LABELS).forEach(p=>{
        document.querySelectorAll('.perm-'+p).forEach(el=>{el.style.display=USER_PERMS[p]?'':'none'});
    });
}
function hasPerm(p){return USER_PERMS[p]===true}
function populateUserMenu(){
    const i=(CURRENT_USER.display_name||CURRENT_USER.username).split(' ').map(w=>w[0]).join('').slice(0,2);
    document.getElementById('userAvatar').textContent=i;
    document.getElementById('userName').textContent=CURRENT_USER.display_name||CURRENT_USER.username;
    document.getElementById('userRole').textContent=CURRENT_USER.role;
}

function switchView(v){
    document.querySelectorAll('.view').forEach(el=>el.classList.remove('active'));
    document.querySelectorAll('.nav-btn').forEach(b=>b.classList.remove('active'));
    document.getElementById('view-'+v).classList.add('active');
    const nb=document.querySelector(`.nav-btn[data-view="${v}"]`);if(nb)nb.classList.add('active');
    if(v==='dashboard')loadDashboard();if(v==='garage')loadCars();
    if(v!=='car-detail')setActiveSidebarCar(null);
    document.getElementById('sidebar').classList.remove('open');
    const ov=document.getElementById('sidebarOverlay');if(ov)ov.classList.remove('open');
    updateMobileNav(v);
}
function toggleSidebar(){
    const s=document.getElementById('sidebar');
    const ov=document.getElementById('sidebarOverlay');
    s.classList.toggle('open');
    if(ov)ov.classList.toggle('open',s.classList.contains('open'));
}
function updateMobileNav(v){
    const map={dashboard:'mobileNavDashboard',garage:'mobileNavGarage','car-detail':'mobileNavGarage'};
    document.querySelectorAll('.mobile-nav-item').forEach(b=>b.classList.remove('active'));
    const activeId=map[v];
    if(activeId){const el=document.getElementById(activeId);if(el)el.classList.add('active');}
}
function triggerMobileAdd(){
    const v=document.querySelector('.view.active');
    if(!v)return;
    const id=v.id;
    if(id==='view-garage')openModal('addCarModal');
    else if(id==='view-car-detail')openAddMaintenanceModal();
    else openModal('addCarModal');
}

// Theme
function applyTheme(){
    const t=userSettings.theme||'dark';
    document.documentElement.setAttribute('data-theme',t);
    const sel=document.getElementById('settingTheme');if(sel)sel.value=t;
}

// Settings tabs
function switchSettingsTab(tab){
    document.querySelectorAll('.settings-tab').forEach(t=>t.classList.remove('active'));
    document.querySelectorAll('.settings-tab-content').forEach(c=>c.classList.remove('active'));
    const tabBtn=document.querySelector(`.settings-tab[onclick*="'${tab}'"]`);
    if(tabBtn)tabBtn.classList.add('active');
    const content=document.getElementById('settingsTab-'+tab);
    if(content)content.classList.add('active');
    if(tab==='users')loadUsers();
    if(tab==='import'){importLoadCars();importGoToStep(1)}
}

// Auth
async function doLogout(){await fetch('/api/auth/logout',{method:'POST'});window.location.href='/login'}
async function changePassword(){
    const c=document.getElementById('currentPw').value,n=document.getElementById('newPw').value,c2=document.getElementById('confirmPw').value;
    if(!c||!n||!c2){toast('Preencha todos os campos','error');return}
    if(n!==c2){toast('As novas senhas não coincidem','error');return}
    if(n.length<4){toast('Mínimo de 4 caracteres','error');return}
    try{const r=await fetch('/api/auth/change-password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({current_password:c,new_password:n})});const d=await r.json();if(!r.ok)throw new Error(d.error);toast('Senha atualizada','success');['currentPw','newPw','confirmPw'].forEach(id=>document.getElementById(id).value='')}catch(e){toast(e.message,'error')}
}
async function forceChangePassword(){
    const n=document.getElementById('forceNewPw').value,c=document.getElementById('forceConfirmPw').value;
    if(!n||!c){toast('Preencha ambos os campos','error');return}
    if(n!==c){toast('As senhas não coincidem','error');return}
    if(n.length<4){toast('Mínimo de 4 caracteres','error');return}
    try{const r=await fetch('/api/auth/change-password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({current_password:'admin',new_password:n})});const d=await r.json();if(!r.ok)throw new Error(d.error);CURRENT_USER.must_change_password=0;toast('Senha atualizada!','success');closeModal('forceChangePwModal')}catch(e){toast(e.message,'error')}
}

// Settings
async function loadSettings(){try{const r=await fetch('/api/settings');userSettings=await r.json()}catch(e){}}
function loadSettingsUI(){
    document.getElementById('settingRange').value=userSettings.dashboard_range||'all';
    document.getElementById('settingShowVehicles').checked=userSettings.show_vehicles!==false;
    document.getElementById('settingShowRecords').checked=userSettings.show_records!==false;
    document.getElementById('settingShowCost').checked=userSettings.show_cost!==false;
    document.getElementById('settingShowDue').checked=userSettings.show_due!==false;
    document.getElementById('settingThemeDark').checked=(userSettings.theme||'dark')==='dark';
}
const saveSettingsDebounced=debounce(async()=>{
    userSettings={dashboard_range:document.getElementById('settingRange').value,show_vehicles:document.getElementById('settingShowVehicles').checked,show_records:document.getElementById('settingShowRecords').checked,show_cost:document.getElementById('settingShowCost').checked,show_due:document.getElementById('settingShowDue').checked,theme:document.getElementById('settingThemeDark').checked?'dark':'light'};
    applyTheme();
    try{await fetch('/api/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(userSettings)});toast('Salvo','success');loadDashboard()}catch(e){toast('Falha','error')}
},500);

function debounce(fn,ms=300){let t;return(...a)=>{clearTimeout(t);t=setTimeout(()=>fn(...a),ms)}}
const debouncedSearchCars=debounce(()=>loadCars());
const debouncedSearchMaintenance=debounce(()=>loadMaintenance());

// Dashboard
async function loadDashboard(){
    try{
        const range=userSettings.dashboard_range||'all';
        const r=await fetch('/api/stats?range='+range);if(r.status===401){window.location.href='/login';return}
        const d=await r.json();
        const cards=document.getElementById('statsGrid').querySelectorAll('.stat-card');
        if(cards[0])cards[0].style.display=userSettings.show_vehicles!==false?'':'none';
        if(cards[1])cards[1].style.display=userSettings.show_records!==false?'':'none';
        if(cards[2])cards[2].style.display=userSettings.show_cost!==false?'':'none';
        if(cards[3])cards[3].style.display=userSettings.show_due!==false?'':'none';
        document.getElementById('statCars').textContent=d.total_cars;
        document.getElementById('statMaintenance').textContent=d.total_maintenance;
        document.getElementById('statCost').textContent=fmtMoney(d.total_cost);
        loadUpcoming();
        const c=document.getElementById('recentActivity');
        if(!d.recent_entries.length){c.innerHTML='<p class="empty-text">Nenhum registro ainda.</p>';return}
        c.innerHTML=d.recent_entries.map(e=>`
            <div class="recent-item" onclick="goToMaintRecord(${e.car_id},${e.id})">
                <span class="recent-badge badge-${e.maintenance_type.toLowerCase()}">${maintLabel(e.maintenance_type)}</span>
                <div class="recent-info"><div class="recent-title">${esc(e.title)}</div><div class="recent-sub">${e.year} ${esc(e.make)} ${esc(e.model)} · ${formatDate(e.service_date)}</div></div>
                ${e.cost?`<span class="recent-cost">${fmtMoney(e.cost)}</span>`:''}
            </div>`).join('');
    }catch(e){console.error(e)}
}
async function goToMaintRecord(carId,maintId){
    currentCarId=carId;
    try{const cr=await fetch('/api/cars/'+carId);const car=await cr.json();
    document.getElementById('carDetailTitle').textContent=`${car.year} ${car.make} ${car.model}`;
    renderCarHero(car);switchView('car-detail');await loadMaintenance();loadVistorias();
    const mr=await fetch('/api/cars/'+carId+'/maintenance');const entries=await mr.json();
    const entry=entries.find(e=>e.id===maintId);if(entry)openMaintDetail(entry)}catch(e){toast('Falha','error')}
}

// Cars
async function loadCars(){
    const q=document.getElementById('carSearch')?.value||'';
    try{const r=await fetch('/api/cars?q='+encodeURIComponent(q));if(r.status===401){window.location.href='/login';return}
    const cars=await r.json();const grid=document.getElementById('carGrid');
    if(!cars.length){grid.innerHTML=q?'<p class="empty-text">Nenhum resultado.</p>':'<p class="empty-text">Nenhum veículo ainda.</p>';return}
    const isAdmin=CURRENT_USER.role==='admin';
    grid.innerHTML=cars.map(car=>`
        <div class="car-card" onclick="openCarDetail(${car.id})">
            <div class="car-card-img">${car.image?`<img src="/uploads/cars/${car.image}" alt="">`:'<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2"><path d="M5 17h14M5 17a2 2 0 01-2-2V7a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2"/><circle cx="7.5" cy="17" r="2.5"/><circle cx="16.5" cy="17" r="2.5"/></svg>'}</div>
            <div class="car-card-body">
                <div class="car-card-name">${car.year} ${esc(car.make)} ${esc(car.model)}</div>
                ${isAdmin&&car.owner_name?`<div class="car-card-owner">${esc(car.owner_name)}</div>`:''}
                ${car.placa?`<div class="car-card-vin">${esc(car.placa)}</div>`:''}
                <div class="car-card-stats"><span>${car.maintenance_count} registros</span><span>${fmtMoney(car.total_cost,0)}</span>${car.latest_odometer?`<span>${Number(car.latest_odometer).toLocaleString()} km</span>`:''}</div>
                ${carCardReminders(car)}
            </div>
            ${hasPerm('can_edit_cars')||hasPerm('can_delete_cars')?`<div class="car-card-actions">${hasPerm('can_edit_cars')?`<button class="btn btn-sm btn-ghost" onclick="event.stopPropagation();openEditCarModal(${car.id})">Editar</button>`:''}${hasPerm('can_delete_cars')?`<button class="btn btn-sm btn-danger" onclick="event.stopPropagation();deleteCar(${car.id},'${esc(car.year)} ${esc(car.make)} ${esc(car.model)}')">Excluir</button>`:''}</div>`:''}
        </div>`).join('')}catch(e){console.error(e)}
}
async function submitCar(e){e.preventDefault();const b=document.getElementById('addCarBtn');b.disabled=true;b.textContent='Adicionando…';try{const r=await fetch('/api/cars',{method:'POST',body:new FormData(e.target)});if(!r.ok){let m='Falha';try{m=(await r.json()).error}catch(x){}throw new Error(m)}toast('Adicionado!','success');e.target.reset();resetPreview('carImagePreview');closeModal('addCarModal');loadCars();loadSidebarCars();loadDashboard()}catch(e){toast(e.message,'error')}finally{b.disabled=false;b.textContent='Adicionar Veículo'}}
async function submitImportCars(e){e.preventDefault();const b=document.getElementById('importCarsBtn');const f=document.getElementById('importCarsFile');if(!f.files.length){toast('Selecione um arquivo','error');return}b.disabled=true;b.textContent='Importando…';try{const fd=new FormData();fd.append('file',f.files[0]);const r=await fetch('/api/cars/import',{method:'POST',body:fd});const d=await r.json();if(!r.ok)throw new Error(d.error);toast(d.imported+' veículos importados'+(d.skipped?', '+d.skipped+' ignorados':''),'success');if(d.errors&&d.errors.length)console.warn(d.errors);closeModal('importCarsModal');e.target.reset();loadCars();loadSidebarCars();loadDashboard()}catch(e){toast(e.message,'error')}finally{b.disabled=false;b.textContent='Importar'}}
async function openEditCarModal(id){try{const r=await fetch('/api/cars/'+id);const c=await r.json();document.getElementById('editCarId').value=c.id;document.getElementById('editCarYear').value=c.year;document.getElementById('editCarMake').value=c.make;document.getElementById('editCarModel').value=c.model;document.getElementById('editCarPlaca').value=c.placa||'';document.getElementById('editCarRenavam').value=c.renavam||'';document.getElementById('editCarChassi').value=c.chassi||'';document.getElementById('editCarCondutor').value=c.condutor||'';document.getElementById('editCarLicenciamento').value=c.licenciamento||'';document.getElementById('editCarIpva').value=c.ipva||'';document.getElementById('editCarCombustivel').value=c.combustivel||'';document.getElementById('editCarCrv').value=c.crv||'';document.getElementById('editCarCrlv').value=c.crlv||'';document.getElementById('editCarSeguro').value=c.seguro||'';document.getElementById('editCarKmAtual').value=c.km_atual!=null?c.km_atual:'';document.getElementById('editCarPurchaseDate').value=c.purchase_date||'';const p=document.getElementById('editCarImagePreview');if(c.image){p.classList.add('has-preview');p.innerHTML=`<img src="/uploads/cars/${c.image}" alt="">`}else{p.classList.remove('has-preview');p.innerHTML='<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg><span>Alterar foto</span>'}openModal('editCarModal')}catch(e){toast('Falha','error')}}
async function submitEditCar(e){e.preventDefault();const id=document.getElementById('editCarId').value;try{const r=await fetch('/api/cars/'+id,{method:'PUT',body:new FormData(e.target)});if(!r.ok){let m='Falha';try{m=(await r.json()).error}catch(x){}throw new Error(m)}toast('Atualizado','success');closeModal('editCarModal');loadCars();loadSidebarCars();if(currentCarId==id)openCarDetail(parseInt(id))}catch(e){toast(e.message,'error')}}
async function deleteCar(id,name){if(!confirm(`Excluir "${name}"?`))return;try{await fetch('/api/cars/'+id,{method:'DELETE'});toast('Excluído','success');loadCars();loadSidebarCars();loadDashboard();if(currentCarId==id)switchView('garage')}catch(e){toast('Falha','error')}}

async function openCarDetail(carId){currentCarId=carId;try{const r=await fetch('/api/cars/'+carId);const car=await r.json();document.getElementById('carDetailTitle').textContent=`${car.year} ${car.make} ${car.model}`;renderCarHero(car);switchView('car-detail');setActiveSidebarCar(carId);loadMaintenance();loadReminders();loadVistorias()}catch(e){toast('Falha','error')}}
function renderCarHero(car){document.getElementById('carDetailHero').innerHTML=`${car.image?`<img src="/uploads/cars/${car.image}" alt="">`:'<div class="placeholder-img"><svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2"><path d="M5 17h14M5 17a2 2 0 01-2-2V7a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2"/><circle cx="7.5" cy="17" r="2.5"/><circle cx="16.5" cy="17" r="2.5"/></svg></div>'}<div class="detail-meta"><div class="detail-meta-row"><div class="detail-meta-item"><span class="label">Ano</span><span class="value">${car.year}</span></div><div class="detail-meta-item"><span class="label">Marca</span><span class="value">${esc(car.make)}</span></div><div class="detail-meta-item"><span class="label">Modelo</span><span class="value">${esc(car.model)}</span></div></div><div class="detail-meta-row">${car.placa?`<div class="detail-meta-item"><span class="label">Placa</span><span class="value mono">${esc(car.placa)}</span></div>`:''}${car.renavam?`<div class="detail-meta-item"><span class="label">RENAVAM</span><span class="value mono">${esc(car.renavam)}</span></div>`:''}${car.chassi?`<div class="detail-meta-item"><span class="label">Chassi</span><span class="value mono">${esc(car.chassi)}</span></div>`:''}${car.condutor?`<div class="detail-meta-item"><span class="label">Principal Condutor</span><span class="value">${esc(car.condutor)}</span></div>`:''}${car.licenciamento?`<div class="detail-meta-item"><span class="label">Licenciamento</span><span class="value">${formatDate(car.licenciamento)}</span></div>`:''}${car.ipva?`<div class="detail-meta-item"><span class="label">IPVA</span><span class="value">${formatDate(car.ipva)}</span></div>`:''}${car.combustivel?`<div class="detail-meta-item"><span class="label">Combustível</span><span class="value">${esc(car.combustivel)}</span></div>`:''}${car.crv?`<div class="detail-meta-item"><span class="label">CRV</span><span class="value mono">${esc(car.crv)}</span></div>`:''}${car.crlv?`<div class="detail-meta-item"><span class="label">CRLV</span><span class="value">${formatDate(car.crlv)}</span></div>`:''}${car.seguro?`<div class="detail-meta-item"><span class="label">Seguro</span><span class="value">${formatDate(car.seguro)}</span></div>`:''}${car.vistoria_data?`<div class="detail-meta-item"><span class="label">Última Vistoria</span><span class="value">${formatDate(car.vistoria_data)}</span></div>`:''}${car.vistoria_validade?`<div class="detail-meta-item"><span class="label">Validade da Vistoria</span><span class="value">${formatDate(car.vistoria_validade)}</span></div>`:''}${car.km_atual!=null?`<div class="detail-meta-item"><span class="label">KM Atual</span><span class="value">${Number(car.km_atual).toLocaleString()}</span></div>`:''}${car.purchase_date?`<div class="detail-meta-item"><span class="label">Comprado em</span><span class="value">${formatDate(car.purchase_date)}</span></div>`:''}</div></div>`}
function exportCarCSV(){if(currentCarId)window.location.href='/api/cars/'+currentCarId+'/export'}
function openImportForCar(){openModal('settingsModal');switchSettingsTab('import');setTimeout(()=>{document.getElementById('importCarSelect').value=currentCarId},200)}

// Maintenance
async function loadMaintenance(){if(!currentCarId)return[];const q=document.getElementById('maintSearch')?.value||'';const s=document.getElementById('maintSort')?.value||'date_desc';try{const r=await fetch(`/api/cars/${currentCarId}/maintenance?q=${encodeURIComponent(q)}&sort=${s}`);const entries=await r.json();const list=document.getElementById('maintenanceList');if(!entries.length){list.innerHTML=q?'<p class="empty-text">Nenhum resultado.</p>':'<p class="empty-text">Nenhum registro ainda.</p>';return entries}list.innerHTML=entries.map(e=>`<div class="maint-card" onclick='openMaintDetail(${JSON.stringify(e).replace(/'/g,"&#39;")})'><div class="maint-type-dot ${e.maintenance_type.toLowerCase()}"></div><div class="maint-title-col"><div class="maint-title">${esc(e.title)}</div><div class="maint-subtitle">${maintLabel(e.maintenance_type)} · ${formatDate(e.service_date)}</div></div><div class="maint-meta-col">${e.odometer?`<div class="maint-meta-item"><div class="val">${Number(e.odometer).toLocaleString()}</div><div class="lbl">Km</div></div>`:''}${e.cost?`<div class="maint-meta-item"><div class="val" style="color:var(--green)">${fmtMoney(e.cost)}</div><div class="lbl">Custo</div></div>`:''}</div></div>`).join('');return entries}catch(e){console.error(e);return[]}}

function openMaintDetail(e){
    const docs=(e.images||[]).filter(i=>i.file_type==='document');
    document.getElementById('viewMaintTitle').textContent=e.title;
    document.getElementById('viewMaintContent').innerHTML=`<div class="view-maint-details"><div class="detail-item"><span class="lbl">Tipo</span><span class="val">${maintLabel(e.maintenance_type)}</span></div><div class="detail-item"><span class="lbl">Data</span><span class="val">${formatDate(e.service_date)}</span></div>${e.odometer?`<div class="detail-item"><span class="lbl">Odômetro</span><span class="val">${Number(e.odometer).toLocaleString()} km</span></div>`:''}${e.parts_vendor?`<div class="detail-item"><span class="lbl">Fornecedor</span><span class="val">${esc(e.parts_vendor)}</span></div>`:''}${e.cost!=null?`<div class="detail-item"><span class="lbl">Custo</span><span class="val">${fmtMoney(e.cost)}</span></div>`:''}</div>${e.notes?`<div class="view-maint-notes">${esc(e.notes)}</div>`:''}${renderMaintGallery(e)}${docs.length?`<div class="view-maint-docs"><div class="view-maint-docs-title">Documentos</div>${docs.map(d=>`<a href="/uploads/maintenance/${d.filename}" target="_blank" class="doc-link"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>${esc(d.original_name||'Documento.pdf')}</a>`).join('')}</div>`:''}`;
    let btns='';
    if(hasPerm('can_delete_records'))btns+=`<button class="btn btn-danger btn-sm" onclick="deleteMaintenance(${e.id})">Excluir</button>`;
    if(hasPerm('can_add_records'))btns+=`<button class="btn btn-ghost btn-sm" onclick="duplicateMaintenance(${e.id})">Duplicar</button>`;
    if(hasPerm('can_edit_records'))btns+=`<button class="btn btn-primary btn-sm" onclick="closeModal('viewMaintModal');openEditMaintModal(${e.id})">Editar</button>`;
    if(!btns)btns=`<button class="btn btn-ghost" onclick="closeModal('viewMaintModal')">Fechar</button>`;
    document.getElementById('viewMaintActions').innerHTML=btns;
    openModal('viewMaintModal');
}

function openAddMaintenanceModal(){document.getElementById('addMaintForm').reset();addMaintPhotos.length=0;renderPickedPhotos('galleryThumbs',addMaintPhotos);document.getElementById('addDocList').innerHTML='';resetPreview('maintGalleryPreview');document.querySelector('#addMaintForm [name="service_date"]').valueAsDate=new Date();loadMaintResetOptions();openModal('addMaintModal')}

async function submitMaintenance(e){e.preventDefault();if(!currentCarId)return;const b=document.getElementById('addMaintBtn');b.disabled=true;b.textContent='Salvando…';const fd=new FormData(e.target);fd.delete('gallery');addMaintPhotos.forEach(f=>fd.append('gallery',f));try{const r=await fetch('/api/cars/'+currentCarId+'/maintenance',{method:'POST',body:fd});if(!r.ok){let m='Falha';try{m=(await r.json()).error}catch(x){}throw new Error(m)}toast('Salvo!','success');closeModal('addMaintModal');loadMaintenance();loadReminders();loadDashboard()}catch(e){toast(e.message,'error')}finally{b.disabled=false;b.textContent='Salvar'}}

async function openEditMaintModal(id){try{const r=await fetch('/api/cars/'+currentCarId+'/maintenance');const entries=await r.json();const e=entries.find(x=>x.id===id);if(!e)return toast('Não encontrado','error');document.getElementById('editMaintId').value=e.id;document.getElementById('editMaintTitle').value=e.title;document.getElementById('editMaintDate').value=e.service_date;document.getElementById('editMaintOdo').value=e.odometer||'';document.getElementById('editMaintVendor').value=e.parts_vendor||'';document.getElementById('editMaintCost').value=e.cost||'';document.getElementById('editMaintNotes').value=e.notes||'';if(e.maintenance_type==='Maintenance')document.getElementById('editMaintTypeMaint').checked=true;else if(e.maintenance_type==='Repair')document.getElementById('editMaintTypeRepair').checked=true;else if(e.maintenance_type==='Upgrade')document.getElementById('editMaintTypeUpgrade').checked=true;else if(e.maintenance_type==='Inspection')document.getElementById('editMaintTypeInspection').checked=true;document.getElementById('editMaintThumbs').innerHTML=maintEditThumbsHtml(e);editMaintPhotos.length=0;renderPickedPhotos('editMaintNewThumbs',editMaintPhotos);openModal('editMaintModal')}catch(e){toast('Falha','error')}}

async function submitEditMaintenance(e){e.preventDefault();const id=document.getElementById('editMaintId').value;try{const fd=new FormData(e.target);fd.delete('gallery');editMaintPhotos.forEach(f=>fd.append('gallery',f));const r=await fetch('/api/maintenance/'+id,{method:'PUT',body:fd});if(!r.ok){let m='Falha';try{m=(await r.json()).error}catch(x){}throw new Error(m)}toast('Atualizado','success');closeModal('editMaintModal');loadMaintenance();loadDashboard()}catch(e){toast(e.message,'error')}}
async function deleteMaintenance(id){if(!confirm('Excluir?'))return;try{await fetch('/api/maintenance/'+id,{method:'DELETE'});toast('Excluído','success');closeModal('viewMaintModal');loadMaintenance();loadDashboard()}catch(e){toast('Falha','error')}}
async function duplicateMaintenance(id){try{const r=await fetch('/api/maintenance/'+id+'/duplicate',{method:'POST'});if(!r.ok){let m='Falha';try{m=(await r.json()).error}catch(x){}throw new Error(m)}toast('Duplicado','success');closeModal('viewMaintModal');loadMaintenance();loadDashboard()}catch(e){toast(e.message,'error')}}

// ── Fotos dos registros (adicionar/remover depois de criados) ──
function maintEditThumbsHtml(e){
    const imgs=(e.images||[]).filter(i=>i.file_type!=='document');
    if(!imgs.length)return'';
    const urls=imgs.map(i=>'/uploads/maintenance/'+i.filename);
    return imgs.map((img,idx)=>`<span class="gallery-thumb-wrap"><img class="gallery-thumb" src="${urls[idx]}" alt="" loading="lazy" onclick='openLightbox(${JSON.stringify(urls)},${idx})'><button type="button" class="thumb-del" title="Remover foto" onclick="event.stopPropagation();removeMaintImage(${e.id},${img.id})">&times;</button></span>`).join('');
}
function renderMaintGallery(e){
    const images=(e.images||[]).filter(i=>i.file_type!=='document');
    const canEdit=hasPerm('can_edit_records');
    if(!images.length&&!canEdit)return'';
    const urls=images.map(i=>'/uploads/maintenance/'+i.filename);
    const items=images.map((img,idx)=>`<div class="img-with-cap"><span class="gallery-thumb-wrap"><img src="${urls[idx]}" alt="" loading="lazy" onclick='openLightbox(${JSON.stringify(urls)},${idx})'>${canEdit?`<button type="button" class="thumb-del" title="Remover foto" onclick="event.stopPropagation();removeMaintImage(${e.id},${img.id})">&times;</button>`:''}</span>${canEdit||img.caption?`<div class="img-cap ${img.caption?'filled':''}" onclick="event.stopPropagation();${canEdit?`editImgCaption(${e.id},${img.id},'maint',this)`:''}">${esc(img.caption||'')||'+ legenda'}</div>`:''}</div>`).join('');
    const tile=canEdit?`<label class="add-photo-tile" title="Adicionar fotos"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 5v14M5 12h14"/></svg><span>Fotos</span><input type="file" accept="image/*" multiple onchange="uploadMaintPhotos(this)" data-mid="${e.id}"></label><label class="add-photo-tile" title="Tirar foto"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z"/><circle cx="12" cy="13" r="4"/></svg><span>Tirar</span><input type="file" accept="image/*" capture="environment" onchange="uploadMaintPhotos(this)" data-mid="${e.id}"></label>`:'';
    return `<div class="view-maint-gallery">${items}${tile}</div>`;
}
async function refreshMaintDetail(id){
    const entries=await loadMaintenance();
    const e=(entries||[]).find(x=>x.id===id);
    if(e)openMaintDetail(e);else closeModal('viewMaintModal');
}
async function refreshMaintEditThumbs(id){
    const entries=await loadMaintenance();
    const e=(entries||[]).find(x=>x.id===id);
    const el=document.getElementById('editMaintThumbs');
    if(e&&el)el.innerHTML=maintEditThumbsHtml(e);
}
async function uploadMaintPhotos(input){
    const mid=Number(input.dataset.mid);
    const files=Array.from(input.files||[]);
    if(!mid||!files.length)return;
    const fd=new FormData();
    files.forEach(f=>fd.append('gallery',f));
    try{
        const r=await fetch('/api/maintenance/'+mid+'/images',{method:'POST',body:fd});
        if(!r.ok){let m='Falha';try{m=(await r.json()).error}catch(x){}throw new Error(m)}
        toast(files.length>1?files.length+' fotos adicionadas':'Foto adicionada','success');
        input.value='';
        await refreshMaintDetail(mid);
    }catch(e){toast(e.message,'error')}
}
async function removeMaintImage(mid,iid){
    if(!confirm('Remover esta foto do registro?'))return;
    try{
        const r=await fetch('/api/maintenance/images/'+iid,{method:'DELETE'});
        if(!r.ok)throw new Error('Falha');
        toast('Foto removida','success');
        if(document.getElementById('viewMaintModal').classList.contains('open'))await refreshMaintDetail(mid);
        else if(document.getElementById('editMaintModal').classList.contains('open'))await refreshMaintEditThumbs(mid);
        else await loadMaintenance();
    }catch(e){toast(e.message||'Falha','error')}
}
function editImgCaption(mid,iid,ctx,el){
    const cur=el.innerText==='+ legenda'?'':el.innerText;
    const v=prompt('Legenda da foto',cur);
    if(v===null)return;
    const url=ctx==='maint'?`/api/maintenance/images/${iid}`:`/api/vistoria/images/${iid}`;
    fetch(url,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({caption:v})})
    .then(r=>{if(!r.ok)throw new Error('Falha');toast('Legenda salva','success');if(ctx==='maint')refreshMaintDetail(mid);else loadVistorias()})
    .catch(e=>toast(e.message,'error'));
}

// ── Vistorias (histórico 1:N por veículo) ───────────
async function refreshCarHero(){
    if(!currentCarId)return;
    try{const r=await fetch('/api/cars/'+currentCarId);if(!r.ok)return;renderCarHero(await r.json())}catch(e){}
}
async function loadVistorias(){
    if(!currentCarId)return;
    const list=document.getElementById('vistoriasList');if(!list)return;
    try{
        const r=await fetch('/api/cars/'+currentCarId+'/vistorias');
        const rows=await r.json();
        if(!r.ok){list.innerHTML='<p class="empty-text">Falha ao carregar as vistorias.</p>';return}
        if(!rows.length){list.innerHTML='<p class="empty-text">Nenhuma vistoria registrada ainda.</p>';return}
        const canDel=hasPerm('can_delete_records');
        list.innerHTML=rows.map(v=>{
            const imgs=(v.images||[]).filter(i=>i.file_type!=='document');
            const docs=(v.images||[]).filter(i=>i.file_type==='document');
            const urls=imgs.map(i=>'/uploads/vistorias/'+i.filename);
            const thumbs=imgs.length?`<div class="vistoria-thumbs">${imgs.map((img,idx)=>`<div class="vistoria-img-item"><span class="vistoria-thumb"><img src="${urls[idx]}" alt="" loading="lazy" onclick='openLightbox(${JSON.stringify(urls)},${idx})'>${canDel?`<button class="vistoria-thumb-del" title="Remover foto" onclick="event.stopPropagation();deleteVistoriaImage(${img.id})">&times;</button>`:''}</span>${canDel||img.caption?`<div class="img-cap ${img.caption?'filled':''}" onclick="event.stopPropagation();${canDel?`editImgCaption(${v.id},${img.id},'vist',this)`:''}">${esc(img.caption||'')||'+ legenda'}</div>`:''}</div>`).join('')}</div>`:'';
            const docLinks=docs.length?`<div class="vistoria-docs">${docs.map(d=>`<a class="doc-link" href="/uploads/vistorias/${d.filename}" target="_blank">📄 ${esc(d.original_name||'Documento.pdf')}</a>`).join('')}</div>`:'';
            return `<div class="vistoria-card">
                <div class="vistoria-head"><div class="vistoria-date">🔍 ${formatDate(v.vistoria_data)}</div>${v.validade?`<div class="vistoria-valid">Validade: ${formatDate(v.validade)}</div>`:''}${canDel?`<button class="btn btn-sm btn-danger vistoria-del" onclick="deleteVistoria(${v.id})">Excluir</button>`:''}</div>
                ${v.observacao?`<div class="vistoria-notes">${esc(v.observacao)}</div>`:''}
                ${thumbs}${docLinks}
            </div>`;
        }).join('');
    }catch(e){console.error(e)}
}
function openAddVistoriaModal(){
    const f=document.getElementById('addVistoriaForm');f.reset();
    document.getElementById('vistoriaThumbs').innerHTML='';
    document.getElementById('vistoriaData').valueAsDate=new Date();
    openModal('addVistoriaModal');
}
async function submitVistoria(e){
    e.preventDefault();if(!currentCarId)return;
    const b=document.getElementById('addVistoriaBtn');b.disabled=true;b.textContent='Salvando…';
    try{
        const r=await fetch('/api/cars/'+currentCarId+'/vistorias',{method:'POST',body:new FormData(e.target)});
        if(!r.ok){let m='Falha';try{m=(await r.json()).error}catch(x){}throw new Error(m)}
        toast('Vistoria registrada!','success');
        e.target.reset();document.getElementById('vistoriaThumbs').innerHTML='';
        closeModal('addVistoriaModal');loadVistorias();refreshCarHero();
    }catch(err){toast(err.message,'error')}finally{b.disabled=false;b.textContent='Salvar'}
}
async function deleteVistoria(id){
    if(!confirm('Excluir esta vistoria e todas as fotos dela?'))return;
    try{const r=await fetch('/api/vistorias/'+id,{method:'DELETE'});if(!r.ok)throw new Error('Falha');toast('Vistoria excluída','success');loadVistorias();refreshCarHero()}catch(e){toast(e.message,'error')}
}
async function deleteVistoriaImage(id){
    if(!confirm('Remover esta foto da vistoria?'))return;
    try{const r=await fetch('/api/vistoria/images/'+id,{method:'DELETE'});if(!r.ok)throw new Error('Falha');toast('Foto removida','success');loadVistorias()}catch(e){toast(e.message,'error')}
}

// Users
async function loadUsers(){if(CURRENT_USER.role!=='admin')return;try{const r=await fetch('/api/users');const users=await r.json();document.getElementById('usersList').innerHTML=users.map(u=>{const i=(u.display_name||u.username).split(' ').map(w=>w[0]).join('').slice(0,2).toUpperCase();const self=u.id===CURRENT_USER.id;return`<div class="user-card"><div class="user-card-avatar role-${u.role}">${i}</div><div class="user-card-info"><div class="user-card-name">${esc(u.display_name||u.username)} ${self?'<span style="color:var(--text-muted);font-size:0.65rem">(você)</span>':''}</div><div class="user-card-meta">@${esc(u.username)} · ${u.role}</div></div><span class="role-badge ${u.role}">${u.role}</span><div class="user-card-actions"><button class="btn btn-sm btn-ghost" onclick="openEditUser(${u.id})">Editar</button>${!self?`<button class="btn btn-sm btn-danger" onclick="deleteUser(${u.id},'${esc(u.username)}')">Excluir</button>`:''}</div></div>`}).join('')}catch(e){console.error(e)}}

function buildPermGrid(prefix,perms){
    const grid=document.getElementById(prefix+'PermGrid');
    grid.innerHTML=Object.entries(PERM_LABELS).map(([k,label])=>`<div class="setting-row"><label>${label}</label><label class="toggle"><input type="checkbox" id="${prefix}Perm_${k}" ${perms[k]?'checked':''}><span class="toggle-slider"></span></label></div>`).join('');
}
function getPermsFromGrid(prefix){
    const perms={};Object.keys(PERM_LABELS).forEach(k=>{const cb=document.getElementById(prefix+'Perm_'+k);perms[k]=cb?cb.checked:false});return perms;
}
function togglePermPanel(prefix){
    const role=document.getElementById(prefix+'Role').value;
    const panel=document.getElementById(prefix+'PermPanel');
    panel.style.display=role==='editor'?'':'none';
    if(role==='editor'){
        const perms=prefix==='new'?{can_add_cars:true,can_edit_cars:true,can_delete_cars:true,can_add_records:true,can_edit_records:true,can_delete_records:true,can_import:false,can_export:true}:getPermsFromGrid(prefix);
        buildPermGrid(prefix,perms);
    }
}

async function submitNewUser(){
    const u=document.getElementById('newUsername').value.trim(),d=document.getElementById('newDisplayName').value.trim(),p=document.getElementById('newPassword').value,r=document.getElementById('newRole').value;
    if(!u||!p){toast('Obrigatório','error');return}
    const perms=r==='editor'?getPermsFromGrid('new'):{};
    try{const res=await fetch('/api/users',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,display_name:d,password:p,role:r,permissions:perms})});const data=await res.json();if(!res.ok)throw new Error(data.error);toast('Criado','success');closeModal('addUserModal');document.getElementById('newUsername').value='';document.getElementById('newDisplayName').value='';document.getElementById('newPassword').value='';loadUsers()}catch(e){toast(e.message,'error')}
}
async function openEditUser(uid){
    try{const r=await fetch('/api/users');const users=await r.json();const u=users.find(x=>x.id===uid);if(!u)return;
    document.getElementById('editUserId').value=u.id;document.getElementById('editUsername').value=u.username;document.getElementById('editDisplayName').value=u.display_name||'';document.getElementById('editRole').value=u.role;document.getElementById('editPassword').value='';
    const panel=document.getElementById('editPermPanel');
    if(u.role==='editor'){panel.style.display='';buildPermGrid('edit',u.effective_permissions||{})}else{panel.style.display='none'}
    openModal('editUserModal')}catch(e){toast('Falha','error')}
}
async function submitEditUser(){
    const id=document.getElementById('editUserId').value,dn=document.getElementById('editDisplayName').value.trim(),role=document.getElementById('editRole').value,pw=document.getElementById('editPassword').value;
    const perms=role==='editor'?getPermsFromGrid('edit'):{};
    const body={display_name:dn,role,permissions:perms};if(pw)body.password=pw;
    try{const r=await fetch('/api/users/'+id,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw new Error(d.error);toast('Atualizado','success');closeModal('editUserModal');loadUsers()}catch(e){toast(e.message,'error')}
}
async function deleteUser(id,un){if(!confirm(`Excluir "${un}"?`))return;try{const r=await fetch('/api/users/'+id,{method:'DELETE'});const d=await r.json();if(!r.ok)throw new Error(d.error);toast('Excluído','success');loadUsers()}catch(e){toast(e.message,'error')}}

// CSV Import
let csvFile=null,csvHeaders=[],importPreviewData=null,importTargetCarId=null;
function importGoToStep(s){for(let i=1;i<=4;i++){document.getElementById('importStep'+i).style.display='none';document.getElementById('importStep'+i+'Indicator').classList.remove('active','done')}document.getElementById('importStep'+s).style.display='';document.getElementById('importStep'+s+'Indicator').classList.add('active');for(let i=1;i<s;i++)document.getElementById('importStep'+i+'Indicator').classList.add('done')}
function importLoadCars(){fetch('/api/cars').then(r=>r.json()).then(cars=>{const sel=document.getElementById('importCarSelect');const cv=sel.value;sel.innerHTML='<option value="">— Selecionar —</option>';cars.forEach(c=>{sel.innerHTML+=`<option value="${c.id}">${c.year} ${esc(c.make)} ${esc(c.model)}</option>`});if(cv)sel.value=cv})}
function onCsvFileSelected(input){const info=document.getElementById('csvFileInfo'),btn=document.getElementById('importNextStep1');if(input.files&&input.files[0]){csvFile=input.files[0];info.style.display='flex';info.innerHTML=`<span class="file-name">${esc(csvFile.name)}</span> (${(csvFile.size/1024).toFixed(1)} KB)`;const reader=new FileReader();reader.onload=e=>{const t=e.target.result;csvHeaders=parseCSVLine(t.split(/\r?\n/)[0]);const rc=t.split(/\r?\n/).filter(l=>l.trim()).length-1;info.innerHTML+=` · ${csvHeaders.length} colunas · ${rc} linhas`};reader.readAsText(csvFile);btn.disabled=!document.getElementById('importCarSelect').value}else{csvFile=null;csvHeaders=[];info.style.display='none';btn.disabled=true}}
document.addEventListener('change',e=>{if(e.target.id==='importCarSelect'){const btn=document.getElementById('importNextStep1');if(btn)btn.disabled=!(e.target.value&&csvFile)}});
function parseCSVLine(l){const r=[];let c='',q=false;for(let i=0;i<l.length;i++){const ch=l[i];if(q){if(ch==='"'&&l[i+1]==='"'){c+='"';i++}else if(ch==='"')q=false;else c+=ch}else{if(ch==='"')q=true;else if(ch===','){r.push(c.trim());c=''}else c+=ch}}r.push(c.trim());return r}
function importGoToMapping(){if(!csvFile||!document.getElementById('importCarSelect').value)return;importTargetCarId=document.getElementById('importCarSelect').value;buildMappingUI();importGoToStep(2)}
function buildMappingUI(){const g=document.getElementById('mappingGrid');const fields=[{key:'title',label:'Título',hint:'Resumo',required:true},{key:'maintenance_type',label:'Tipo',hint:'Reparo/Manutenção/Melhoria/Vistoria'},{key:'service_date',label:'Data do Serviço',hint:'YYYY-MM-DD',required:true},{key:'odometer',label:'Odômetro',hint:'Quilometragem'},{key:'parts_vendor',label:'Fornecedor',hint:'Origem'},{key:'cost',label:'Custo',hint:'Valor'},{key:'notes',label:'Observações',hint:'Detalhes'}];g.innerHTML=fields.map(f=>{const opts=csvHeaders.map(h=>`<option value="${esc(h)}" ${isAutoMatch(h,f.key)?'selected':''}>${esc(h)}</option>`).join('');return`<div class="mapping-row ${f.required?'required':''}"><div class="mapping-field-label">${f.required?'<span class="req-dot"></span>':'<span style="width:6px"></span>'}<span>${f.label}</span><span class="field-hint">${f.hint}</span></div><div class="mapping-arrow"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg></div><select class="mapping-select" data-field="${f.key}"><option value="">— Ignorar —</option>${opts}</select></div>`}).join('')}
function isAutoMatch(h,k){const n=h.toLowerCase().replace(/[_\-\s]+/g,'');const m={title:['title','name','description','summary'],maintenance_type:['type','maintenancetype','category'],service_date:['date','servicedate'],odometer:['odometer','mileage','miles','odo'],parts_vendor:['vendor','partsvendor','supplier','shop'],cost:['cost','price','amount','total'],notes:['notes','comment','comments','memo']};return(m[k]||[]).some(x=>n===x||n.includes(x))}
function getMapping(){const m={};document.querySelectorAll('.mapping-select').forEach(s=>{if(s.value)m[s.value]=s.dataset.field});return m}
async function importRunDryRun(){const m=getMapping();const mv=Object.values(m);if(!mv.includes('title')){toast('Mapeie o campo Título','error');return}if(!mv.includes('service_date')){toast('Mapeie o campo Data','error');return}const btn=document.getElementById('importNextStep2');btn.disabled=true;btn.textContent='…';try{const fd=new FormData();fd.append('file',csvFile);fd.append('mapping',JSON.stringify(m));fd.append('car_id',importTargetCarId);const r=await fetch('/api/import/preview',{method:'POST',body:fd});const d=await r.json();if(!r.ok)throw new Error(d.error);importPreviewData=d;renderDryRunPreview(d);importGoToStep(3)}catch(e){toast(e.message,'error')}finally{btn.disabled=false;btn.textContent='Pré-visualizar →'}}
function renderDryRunPreview(d){const s=document.getElementById('importSummary');const inv=d.row_count-d.valid_count;s.innerHTML=`<div class="import-summary-stat"><span class="val">${d.row_count}</span><span class="lbl">Total</span></div><div class="import-summary-stat good"><span class="val">${d.valid_count}</span><span class="lbl">Válidos</span></div>${inv?`<div class="import-summary-stat bad"><span class="val">${inv}</span><span class="lbl">Inválidos</span></div>`:''}`;const eb=document.getElementById('importErrors');if(d.errors.length){eb.style.display='';document.getElementById('importErrorCount').textContent=d.errors.length+' aviso(s)';document.getElementById('importErrorsList').innerHTML=d.errors.map(e=>esc(e)).join('<br>')}else eb.style.display='none';const h=document.getElementById('importPreviewHead'),b=document.getElementById('importPreviewBody');h.innerHTML=['','Linha','Título','Tipo','Data','Odô','Fornecedor','Custo','Problemas'].map(c=>`<th>${c}</th>`).join('');b.innerHTML=d.preview_rows.map(r=>`<tr class="${r._valid?'row-valid':'row-invalid'}"><td><span class="row-status ${r._valid?'valid':'invalid'}"></span></td><td>${r._row_num}</td><td>${esc(r.title)||'—'}</td><td>${esc(maintLabel(r.maintenance_type))}</td><td>${r.service_date||'—'}</td><td>${r.odometer!=null?Number(r.odometer).toLocaleString():'—'}</td><td>${esc(r.parts_vendor)||'—'}</td><td>${r.cost!=null?fmtMoney(r.cost):'—'}</td><td>${r._errors.length?`<span class="cell-error">${esc(r._errors.join('; '))}</span>`:'✓'}</td></tr>`).join('');const cb=document.getElementById('importCommitBtn');cb.disabled=d.valid_count===0;cb.innerHTML=d.valid_count?`Importar ${d.valid_count}`:'Nenhum'}
async function importCommit(){if(!importPreviewData||!importPreviewData.valid_count)return;const btn=document.getElementById('importCommitBtn');btn.disabled=true;btn.innerHTML='…';try{const r=await fetch('/api/import/commit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({car_id:importTargetCarId,rows:importPreviewData.preview_rows})});const d=await r.json();if(!r.ok)throw new Error(d.error);document.getElementById('importDoneMsg').textContent=`${d.imported} importado(s).${d.skipped?' '+d.skipped+' ignorado(s).':''}`;importGoToStep(4);loadDashboard()}catch(e){toast(e.message,'error');btn.disabled=false;btn.innerHTML='Tentar novamente'}}
function importReset(){csvFile=null;csvHeaders=[];importPreviewData=null;importTargetCarId=null;document.getElementById('csvFileInput').value='';document.getElementById('csvFileInfo').style.display='none';document.getElementById('importNextStep1').disabled=true;importLoadCars();importGoToStep(1)}
function importViewCar(){if(importTargetCarId){closeModal('settingsModal');openCarDetail(parseInt(importTargetCarId))}}

// Modals
function openModal(id){
    document.getElementById(id).classList.add('open');document.body.style.overflow='hidden';
    if(id==='settingsModal')loadSettingsUI();
}
function closeModal(id){if(id==='forceChangePwModal'&&CURRENT_USER.must_change_password)return;document.getElementById(id).classList.remove('open');document.body.style.overflow=''}
document.addEventListener('click',e=>{if(e.target.classList.contains('modal-overlay')){if(e.target.id==='forceChangePwModal')return;e.target.classList.remove('open');document.body.style.overflow=''}});
document.addEventListener('keydown',e=>{if(e.key==='Escape'){document.querySelectorAll('.modal-overlay.open').forEach(m=>{if(m.id==='forceChangePwModal')return;m.classList.remove('open')});closeLightbox();document.body.style.overflow=''}});

// File Previews
function previewFile(input,pid){const p=document.getElementById(pid);if(input.files&&input.files[0]){const r=new FileReader();r.onload=e=>{p.classList.add('has-preview');p.innerHTML=`<img src="${e.target.result}" alt="">`};r.readAsDataURL(input.files[0])}}
function resetPreview(id){const p=document.getElementById(id);if(!p)return;p.classList.remove('has-preview');p.innerHTML='<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg><span>Enviar</span>'}
let addMaintPhotos=[],editMaintPhotos=[];
function renderPickedPhotos(listId,arr){const c=document.getElementById(listId);if(!c)return;c.innerHTML='';arr.forEach((f,idx)=>{const r=new FileReader();r.onload=e=>{const img=document.createElement('img');img.src=e.target.result;img.className='gallery-thumb';img.style.cursor='pointer';img.title='Clique para remover';img.onclick=()=>{arr.splice(idx,1);renderPickedPhotos(listId,arr)};c.appendChild(img)};r.readAsDataURL(f);});}
function addMaintPhotoFiles(input){if(input.files)for(const f of input.files)addMaintPhotos.push(f);input.value='';renderPickedPhotos('galleryThumbs',addMaintPhotos)}
function addEditMaintPhotoFiles(input){if(input.files)for(const f of input.files)editMaintPhotos.push(f);input.value='';renderPickedPhotos('editMaintNewThumbs',editMaintPhotos)}
function previewGallery(input,listId='galleryThumbs',src){const c=document.getElementById(listId);const source=src||listId;c.querySelectorAll('img[data-src="'+source+'"]').forEach(n=>n.remove());if(input.files)Array.from(input.files).forEach(f=>{const r=new FileReader();r.onload=e=>{const img=document.createElement('img');img.src=e.target.result;img.className='gallery-thumb';img.dataset.src=source;c.appendChild(img)};r.readAsDataURL(f)})}
function previewDocuments(input,listId){const c=document.getElementById(listId);c.innerHTML='';if(input.files)Array.from(input.files).forEach(f=>{c.innerHTML+=`<div class="doc-item"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>${esc(f.name)}</div>`})}

// Lightbox
function openLightbox(imgs,idx){lightboxImages=imgs;lightboxIndex=idx;document.getElementById('lightboxImg').src=imgs[idx];document.getElementById('lightbox').classList.add('open');document.body.style.overflow='hidden'}
function closeLightbox(){document.getElementById('lightbox').classList.remove('open');document.body.style.overflow=''}
function lightboxPrev(){lightboxIndex=(lightboxIndex-1+lightboxImages.length)%lightboxImages.length;document.getElementById('lightboxImg').src=lightboxImages[lightboxIndex]}
function lightboxNext(){lightboxIndex=(lightboxIndex+1)%lightboxImages.length;document.getElementById('lightboxImg').src=lightboxImages[lightboxIndex]}

function toast(msg,type='success'){const c=document.getElementById('toastContainer'),el=document.createElement('div');el.className='toast '+type;el.textContent=msg;c.appendChild(el);setTimeout(()=>el.remove(),3500)}
function esc(s){if(!s)return'';const d=document.createElement('div');d.textContent=s;return d.innerHTML}
function formatDate(s){if(!s)return'—';const d=new Date(s+(s.includes('T')?'':'T00:00:00'));return d.toLocaleDateString('pt-BR',{year:'numeric',month:'short',day:'numeric'})}
function fmtMoney(v,dec=2){return Number(v||0).toLocaleString('pt-BR',{style:'currency',currency:'BRL',minimumFractionDigits:dec,maximumFractionDigits:dec})}
const MAINT_TYPES={Maintenance:'Manutenção',Repair:'Reparo',Upgrade:'Melhoria',Inspection:'Vistoria'};
function maintLabel(t){return MAINT_TYPES[t]||t}

// ── Service Reminders ──────────────────────────────
const MONTH_DAYS=30.44;
// Renders the countdown for either interval mode; the server hands us
// miles_remaining or days_remaining depending on interval_type.
function reminderCountdown(r){
    const n=v=>Number(v).toLocaleString();
    if(r.interval_type==='time'){
        const rem=r.days_remaining;
        if(rem==null)return{big:'\u2014',lbl:'sem referência'};
        const a=Math.abs(rem);
        if(rem<=0)return{big:n(a),lbl:a===1?'dia atrasado':'dias atrasados'};
        if(a<60)return{big:n(a),lbl:a===1?'dia restante':'dias restantes'};
        const mo=Math.round(a/MONTH_DAYS);
        return{big:n(mo),lbl:mo===1?'mês restante':'meses restantes'};
    }
    const rem=r.miles_remaining;
    if(rem==null)return{big:'\u2014',lbl:'sem referência'};
    if(rem<=0)return{big:n(Math.abs(rem)),lbl:'km atrasados'};
    return{big:n(rem),lbl:'km restantes'};
}
function reminderSub(r){
    const n=v=>Number(v).toLocaleString();
    if(r.interval_type==='time'){
        const mo=Number(r.interval_months)||0;
        const every=`A cada ${n(mo)} ${mo===1?'mês':'meses'}`;
        return r.next_due_date?`${every} \u00b7 próximo em ${formatDate(r.next_due_date)}`
                              :`${every} \u00b7 adicione um registro de serviço ou uma data da última realização`;
    }
    const every=`A cada ${n(r.interval_miles)} km`;
    return r.next_due_odometer!=null?`${every} \u00b7 próximo em ${n(r.next_due_odometer)} km`
                                    :`${every} \u00b7 adicione um registro de serviço ou uma quilometragem da última realização`;
}
function reminderCard(r,showCar){
    const f=r.remaining_fraction;
    const pct=f==null?0:Math.max(0,Math.min(100,Math.round((1-f)*100)));
    const {big,lbl}=reminderCountdown(r);
    return `<div class="reminder-card ${r.status}">
        <div class="reminder-main">
            ${showCar&&r.car_name?`<div class="reminder-car">${esc(r.car_name)}</div>`:''}
            <div class="reminder-title">${esc(r.title)}${r.status==='overdue'?'<span class="reminder-badge">Atrasado</span>':''}</div>
            <div class="reminder-sub">${reminderSub(r)}</div>
            ${f!=null?`<div class="reminder-bar"><span style="width:${pct}%"></span></div>`:''}
        </div>
        <div class="reminder-meta"><div class="reminder-remaining">${big}</div><div class="reminder-lbl">${lbl}</div></div>
        ${showCar?'':`<div class="reminder-actions">
            ${hasPerm('can_edit_records')?`<button class="btn btn-sm btn-ghost" title="Editar" onclick='openEditReminderModal(${JSON.stringify(r).replace(/'/g,"&#39;")})'><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.12 2.12 0 013 3L12 15l-4 1 1-4z"/></svg></button>`:''}
            ${hasPerm('can_delete_records')?`<button class="btn btn-sm btn-ghost" title="Excluir" onclick="deleteReminder(${r.id})"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg></button>`:''}
        </div>`}
    </div>`;
}
async function loadReminders(){
    if(!currentCarId)return;
    try{
        const r=await fetch(`/api/cars/${currentCarId}/reminders`);const list=await r.json();
        const el=document.getElementById('remindersList');
        el.innerHTML=list.length?list.map(x=>reminderCard(x,false)).join(''):'<p class="empty-text">Nenhum lembrete ainda.</p>';
    }catch(e){console.error(e)}
}
// Flips a reminder form between the two interval modes. Fields for the
// inactive mode are disabled so they neither block validation while hidden nor
// get posted -- on an edit that leaves the stored values untouched.
function setReminderMode(prefix,isTime){
    const f=document.getElementById(prefix+'ReminderForm');
    f.querySelectorAll('[data-mode]').forEach(g=>{
        const on=(g.dataset.mode==='time')===isTime;
        g.classList.toggle('hidden',!on);
        g.querySelectorAll('input').forEach(i=>{i.disabled=!on});
    });
    f.querySelectorAll('[data-mode-lbl]').forEach(l=>
        l.classList.toggle('active',(l.dataset.modeLbl==='time')===isTime));
}
function reminderBody(form){
    const b=Object.fromEntries(new FormData(form).entries());
    delete b.id;delete b.interval_type_time;
    b.interval_type=form.interval_type_time.checked?'time':'miles';
    return b;
}
function openAddReminderModal(){
    document.getElementById('addReminderForm').reset();
    setReminderMode('add',false);
    openModal('addReminderModal');
}
async function submitReminder(e){
    e.preventDefault();if(!currentCarId)return;
    const b=document.getElementById('addReminderBtn');b.disabled=true;b.textContent='Salvando\u2026';
    try{
        const r=await fetch(`/api/cars/${currentCarId}/reminders`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(reminderBody(e.target))});
        if(!r.ok){let m='Falha';try{m=(await r.json()).error}catch(x){}throw new Error(m)}
        toast('Lembrete adicionado','success');closeModal('addReminderModal');loadReminders()
    }catch(e){toast(e.message,'error')}finally{b.disabled=false;b.textContent='Salvar'}
}
function openEditReminderModal(r){
    const f=document.getElementById('editReminderForm');f.reset();
    document.getElementById('editReminderId').value=r.id;
    f.title.value=r.title;
    f.interval_miles.value=r.interval_miles||'';
    f.interval_months.value=r.interval_months||'';
    f.last_done_odometer.value=r.last_done_odometer==null?'':r.last_done_odometer;
    f.last_done_date.value=r.last_done_date||'';
    f.notes.value=r.notes||'';
    f.interval_type_time.checked=r.interval_type==='time';
    setReminderMode('edit',f.interval_type_time.checked);
    openModal('editReminderModal');
}
async function submitEditReminder(e){
    e.preventDefault();
    const id=document.getElementById('editReminderId').value;
    try{
        const r=await fetch('/api/reminders/'+id,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(reminderBody(e.target))});
        if(!r.ok){let m='Falha';try{m=(await r.json()).error}catch(x){}throw new Error(m)}
        toast('Lembrete atualizado','success');closeModal('editReminderModal');loadReminders()
    }catch(e){toast(e.message,'error')}
}
async function deleteReminder(id){
    if(!confirm('Excluir este lembrete?'))return;
    try{
        const r=await fetch('/api/reminders/'+id,{method:'DELETE'});
        if(!r.ok)throw new Error('Falha');
        toast('Excluído','success');loadReminders()
    }catch(e){toast('Falha','error')}
}
// ── Counter resets while logging a record ──────────
// The Add Record modal lists this car's counters so the user can restart any
// of them from the record being logged, rather than relying on the title match.
let maintResetReminders=[];
async function loadMaintResetOptions(){
    maintResetReminders=[];
    const block=document.getElementById('maintResetBlock'),list=document.getElementById('maintResetList');
    if(!block)return;
    block.classList.add('hidden');list.innerHTML='';
    if(!currentCarId)return;
    try{
        const r=await fetch(`/api/cars/${currentCarId}/reminders`);if(!r.ok)return;
        maintResetReminders=await r.json();
    }catch(e){return}
    if(!maintResetReminders.length)return;
    block.classList.remove('hidden');
    renderMaintResetOptions();
}
function renderMaintResetOptions(){
    const list=document.getElementById('maintResetList');
    if(!list||!maintResetReminders.length)return;
    const f=document.getElementById('addMaintForm');
    const odo=(f.odometer.value||'').trim(),sd=f.service_date.value;
    // keep whatever is already ticked as the odometer/date are edited
    const ticked=new Set([...list.querySelectorAll('input:checked')].map(i=>i.value));
    list.innerHTML=maintResetReminders.map(r=>{
        const time=r.interval_type==='time',val=time?sd:odo;
        const to=val?(time?`\u2192 ${formatDate(val)}`:`\u2192 ${Number(val).toLocaleString()} km`)
                    :(time?'defina primeiro a data do serviço':'informe primeiro a quilometragem');
        return `<label class="reset-row${val?'':' disabled'}">
            <input type="checkbox" name="reset_reminders" value="${r.id}"${val?'':' disabled'}${val&&ticked.has(String(r.id))?' checked':''}>
            <span class="reset-name">${esc(r.title)}</span>
            <span class="reset-to">${to}</span>
        </label>`;
    }).join('');
}
async function loadUpcoming(){
    try{
        const r=await fetch('/api/reminders/upcoming');const d=await r.json();
        const due=(d.overdue||0)+(d.due_soon||0);
        const s=document.getElementById('statDue');if(s)s.textContent=due;
        const el=document.getElementById('upcomingList');if(!el)return;
        const list=(d.reminders||[]).filter(x=>x.status!=='no_baseline').slice(0,8);
        el.innerHTML=list.length?list.map(x=>reminderCard(x,true)).join(''):'<p class="empty-text">Nada devido. Adicione lembretes na página de um veículo.</p>';
    }catch(e){console.error(e)}
}

// ── Sidebar vehicle list ───────────────────────────
async function loadSidebarCars(){
    // deliberately not reusing loadCars(): that one honours the garage search
    // box and early-returns on no matches, which would blank the sidebar.
    try{
        const r=await fetch('/api/cars');if(!r.ok)return;
        const cars=await r.json();
        const el=document.getElementById('sidebarCars');if(!el)return;
        el.innerHTML=cars.map(c=>{
            const name=`${c.year} ${c.make} ${c.model}`;
            return `<button class="nav-car" data-car="${c.id}" onclick="openCarDetail(${c.id})" title="${esc(name)}"><span class="nav-car-name">${esc(name)}</span></button>`;
        }).join('');
        setActiveSidebarCar(currentCarId);
    }catch(e){console.error(e)}
}
function setActiveSidebarCar(id){
    document.querySelectorAll('.nav-car').forEach(b=>b.classList.toggle('active',id!=null&&String(b.dataset.car)===String(id)));
}

function carCardReminders(car){
    const rs=car.reminders||[];
    if(!rs.length)return '';
    const more=(car.reminders_total||0)-rs.length;
    const rows=rs.map(r=>{
        let txt;
        if(r.interval_type==='time'){
            const a=Math.abs(r.days_remaining);
            txt=(a<60?`${a.toLocaleString()} ${a===1?'dia':'dias'}`:`${Math.round(a/MONTH_DAYS)} ${Math.round(a/MONTH_DAYS)===1?'mês':'meses'}`)+(r.days_remaining<=0?' atrasado':'');
        }else{
            const a=Math.abs(r.miles_remaining);
            txt=`${a.toLocaleString()} km`+(r.miles_remaining<=0?' atrasado':'');
        }
        return `<div class="car-card-rem ${r.status}"><span class="car-card-rem-name">${esc(r.title)}</span><span class="car-card-rem-val">${txt}</span></div>`;
    }).join('');
    return `<div class="car-card-rems"><div class="car-card-rems-hd">Próximos Serviços</div>${rows}${more>0?`<div class="car-card-rem-more">+${more} mais</div>`:''}</div>`;
}

"""Local Tk desktop: edit config, run Fake CLI, browse immutable Job evidence."""
import json
import queue
import subprocess
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from PIL import Image,ImageTk
from mye_c_automation.paths import config_root,data_root,initialize_data
from mye_c_automation.configuration import initialize_config
from mye_c_automation.desktop_data import (load_connection_form,save_connection_form,worker_environment,
    cli_python,fake_command,list_jobs,load_job,image_pairs,status_label)

SCENARIOS={'同照片优先替换':'twin','大边框删除':'frame','局部覆盖字修复':'repair','合格图片保留':'keep'}
ACTION_LABELS={'REPLACE_TWIN':'替换为已有干净版本','DELETE':'删除图片','REMOVE_TEXT':'局部修复','AI_REGENERATE':'图像重绘','SKU_ASSIGN':'SKU 图片分配'}
CHECK_LABELS={'SITE_CONFIG_INCOMPLETE':'请填写后台地址、账号和密码','MODEL_API_KEY_MISSING':'请填写本次会话的模型密钥',
    'MODEL_CONFIG_INVALID':'模型网关配置无效','AUTOMATION_CONFIG_INVALID':'自动化范围配置无效','IMAGE_OPTIONS_INVALID':'图片选项无效',
    'LAMA_MODEL_MISSING':'LaMa 文件不存在','LAMA_CHECKSUM_MISMATCH':'LaMa 文件校验不一致','LAMA_NOT_CONFIGURED':'尚未安装独立 LaMa 权重',
    'LOCAL_REPAIR_RIGHTS_NOT_CONFIRMED':'图片处理权利尚未确认','REPLACE_TWIN_DISABLED':'已有干净版本替换权限未启用'}

class DesktopApp:
    def __init__(self,root,config_directory=None,data_directory=None):
        self.root=root;self.config_directory=config_root(config_directory);self.data_directory=initialize_data(data_directory)
        self.events=queue.Queue();self.worker=None;self.started=None;self.photos=[];self.pairs=[];self.rows=[];self.last_job_id=None
        root.title('MyE-C Automation · 商品图片助手');root.geometry('1160x780');root.minsize(980,680)
        style=ttk.Style(root);style.theme_use('clam');style.configure('TLabel',font=('Microsoft YaHei UI',10));style.configure('TButton',font=('Microsoft YaHei UI',10),padding=(12,7))
        style.configure('Title.TLabel',font=('Microsoft YaHei UI',20,'bold'));style.configure('Hint.TLabel',foreground='#526277')
        shell=ttk.Frame(root,padding=20);shell.pack(fill='both',expand=True)
        ttk.Label(shell,text='商品图片助手',style='Title.TLabel').pack(anchor='w')
        ttk.Label(shell,text='本地配置 · 模拟运行 · 任务证据与图片对比',style='Hint.TLabel').pack(anchor='w',pady=(4,14))
        self.tabs=ttk.Notebook(shell);self.tabs.pack(fill='both',expand=True)
        self.config_tab=ttk.Frame(self.tabs,padding=18);self.tasks_tab=ttk.Frame(self.tabs,padding=18);self.compare_tab=ttk.Frame(self.tabs,padding=18)
        self.tabs.add(self.config_tab,text='  连接与配置  ');self.tabs.add(self.tasks_tab,text='  任务与进度  ');self.tabs.add(self.compare_tab,text='  图片对比  ')
        self._configuration();self._tasks();self._comparison()
        self.status=tk.StringVar(value='就绪。当前界面仅执行离线检查和模拟任务。')
        ttk.Label(shell,textvariable=self.status,style='Hint.TLabel',wraplength=1080).pack(fill='x',pady=(12,0))
        root.protocol('WM_DELETE_WINDOW',self.close);root.after(150,self.poll)
        self.reload_form();self.refresh_jobs()

    def _configuration(self):
        tab=self.config_tab;tab.columnconfigure(1,weight=1)
        ttk.Label(tab,text='连接信息',font=('Microsoft YaHei UI',13,'bold')).grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,10))
        self.form={}
        for row,(key,label,secret) in enumerate([('base','后台 HTTPS 地址',False),('user','后台账号',False),('pwd','后台密码',True),('gateway','模型网关地址',False),('key','模型密钥（仅本次会话）',True)],1):
            ttk.Label(tab,text=label).grid(row=row,column=0,sticky='w',pady=8,padx=(0,16))
            value=tk.StringVar();self.form[key]=value
            ttk.Entry(tab,textvariable=value,show='●' if secret else '').grid(row=row,column=1,sticky='ew',pady=8)
        ttk.Label(tab,text='密码保存在本地站点配置；模型密钥只传给当前界面的子进程，不写入文件。',style='Hint.TLabel',wraplength=900).grid(row=6,column=0,columnspan=2,sticky='w',pady=10)
        buttons=ttk.Frame(tab);buttons.grid(row=7,column=0,columnspan=2,sticky='w',pady=(5,10))
        ttk.Button(buttons,text='创建缺失配置',command=self.init_config).pack(side='left',padx=(0,8))
        ttk.Button(buttons,text='重新加载',command=self.reload_form).pack(side='left',padx=(0,8))
        ttk.Button(buttons,text='保存本地连接配置',command=self.save_form).pack(side='left',padx=(0,8))
        ttk.Button(buttons,text='离线检查',command=self.check_config).pack(side='left')
        ttk.Label(tab,text='配置目录：'+str(self.config_directory),style='Hint.TLabel',wraplength=1000).grid(row=8,column=0,columnspan=2,sticky='w',pady=5)
        self.config_result=tk.Text(tab,height=11,wrap='word',font=('Microsoft YaHei UI',10),background='#f3f6fa',relief='flat',padx=12,pady=10)
        self.config_result.grid(row=9,column=0,columnspan=2,sticky='nsew',pady=10);tab.rowconfigure(9,weight=1)
        ttk.Label(tab,text='真实后台审核和商品写入尚待独立授权；此界面不会自动连接或保存线上商品。',style='Hint.TLabel',wraplength=1000).grid(row=10,column=0,columnspan=2,sticky='w')

    def _tasks(self):
        tab=self.tasks_tab;bar=ttk.Frame(tab);bar.pack(fill='x')
        ttk.Label(bar,text='模拟场景').pack(side='left',padx=(0,10));self.scenario=tk.StringVar(value='同照片优先替换')
        ttk.Combobox(bar,textvariable=self.scenario,values=list(SCENARIOS),state='readonly',width=22).pack(side='left',padx=(0,10))
        self.run_button=ttk.Button(bar,text='开始本地模拟',command=self.start_fake);self.run_button.pack(side='left',padx=(0,8))
        ttk.Button(bar,text='刷新任务',command=self.refresh_jobs).pack(side='left',padx=(0,8))
        ttk.Button(bar,text='选择任务数据目录',command=self.choose_data).pack(side='left')
        self.data_text=tk.StringVar(value='数据目录：'+str(self.data_directory));ttk.Label(tab,textvariable=self.data_text,style='Hint.TLabel').pack(anchor='w',pady=10)
        self.progress=ttk.Progressbar(tab,mode='indeterminate');self.progress.pack(fill='x',pady=(0,10))
        self.jobs=ttk.Treeview(tab,columns=('pid','shop','state'),show='tree headings',height=8)
        self.jobs.heading('#0',text='任务编号');self.jobs.heading('pid',text='商品');self.jobs.heading('shop',text='店铺');self.jobs.heading('state',text='状态')
        self.jobs.column('#0',width=360);self.jobs.column('pid',width=70);self.jobs.column('shop',width=70);self.jobs.column('state',width=290)
        self.jobs.pack(fill='x');self.jobs.bind('<<TreeviewSelect>>',self.select_job)
        self.task_detail=tk.Text(tab,height=9,wrap='word',font=('Microsoft YaHei UI',10),background='#f3f6fa',relief='flat',padx=12,pady=10);self.task_detail.pack(fill='both',expand=True,pady=(10,0))

    def _comparison(self):
        tab=self.compare_tab;bar=ttk.Frame(tab);bar.pack(fill='x',pady=(0,10))
        ttk.Label(bar,text='图片处理记录').pack(side='left',padx=(0,10));self.pair_selection=tk.StringVar()
        self.pair_box=ttk.Combobox(bar,textvariable=self.pair_selection,state='readonly',width=70);self.pair_box.pack(side='left',fill='x',expand=True)
        self.pair_box.bind('<<ComboboxSelected>>',lambda e:self.show_pair())
        panels=ttk.Frame(tab);panels.pack(fill='both',expand=True);panels.columnconfigure(0,weight=1);panels.columnconfigure(1,weight=1);panels.rowconfigure(1,weight=1)
        ttk.Label(panels,text='处理前',font=('Microsoft YaHei UI',12,'bold')).grid(row=0,column=0,pady=10)
        ttk.Label(panels,text='处理后 / 已有干净版本',font=('Microsoft YaHei UI',12,'bold')).grid(row=0,column=1,pady=10)
        self.before_label=ttk.Label(panels,text='请在任务页选择一个已完成任务',anchor='center');self.before_label.grid(row=1,column=0,sticky='nsew',padx=(0,8))
        self.after_label=ttk.Label(panels,text='图片从本地任务证据读取',anchor='center');self.after_label.grid(row=1,column=1,sticky='nsew',padx=(8,0))
        self.picture_note=tk.StringVar(value='图片只读展示，不下载外部图片，不修改任务证据。')
        ttk.Label(tab,textvariable=self.picture_note,style='Hint.TLabel',wraplength=1020).pack(fill='x',pady=(10,0))

    def set_text(self,widget,text):
        widget.configure(state='normal');widget.delete('1.0','end');widget.insert('end',text);widget.configure(state='disabled')

    def init_config(self):
        try:
            result=initialize_config(self.config_directory);self.reload_form()
            self.status.set('已创建 '+str(len(result['created']))+' 个配置，保留 '+str(len(result['preserved']))+' 个已有文件。')
        except (OSError,ValueError):messagebox.showerror('配置初始化失败','请检查目录权限和配置文件。')

    def reload_form(self):
        try:
            values=load_connection_form(self.config_directory);self.revisions=values['revisions']
            for key in ('base','user','pwd','gateway'):self.form[key].set(values[key])
            self.set_text(self.config_result,'连接配置已加载。填写后保存，再进行离线检查。')
        except (OSError,ValueError,TypeError):
            self.revisions={};self.set_text(self.config_result,'尚无完整配置。请先点击“创建缺失配置”。')

    def save_form(self):
        try:
            result=save_connection_form(self.config_directory,{k:self.form[k].get() for k in ('base','user','pwd','gateway')},self.revisions)
            self.revisions=result['revisions'];self.status.set('本地连接配置已保存。未连接后台，未改变自动化授权。')
        except (OSError,ValueError,TypeError):messagebox.showerror('未保存','配置可能已在其他窗口修改，或地址格式无效。请重新加载后检查；已有授权配置不会被改写。')

    def check_config(self):
        self.start_worker([cli_python(),'-u','-m','mye_c_automation','configure','check','--directory',str(self.config_directory)],'check')

    def start_fake(self):self.start_worker(fake_command(SCENARIOS[self.scenario.get()],self.data_directory),'fake')

    def start_worker(self,argv,kind):
        if self.worker is not None:
            messagebox.showinfo('任务进行中','请等待当前任务结束。');return
        self.started=time.monotonic();self.worker=kind;self.run_button.configure(state='disabled');self.progress.start(15)
        self.status.set('正在离线检查…' if kind=='check' else '正在运行本地模拟，不访问线上商品…')
        env=worker_environment(self.form['key'].get())
        def execute():
            try:
                options={'creationflags':subprocess.CREATE_NO_WINDOW} if hasattr(subprocess,'CREATE_NO_WINDOW') else {}
                p=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',env=env,**options)
                stdout,stderr=p.communicate();self.events.put((kind,p.returncode,stdout))
            except OSError:self.events.put((kind,2,''))
        threading.Thread(target=execute,daemon=True).start()

    def poll(self):
        try:
            kind,code,output=self.events.get_nowait()
            self.worker=None;self.progress.stop();self.run_button.configure(state='normal')
            try:result=json.loads(output.strip().splitlines()[-1])
            except (ValueError,IndexError):result={}
            if kind=='check':
                lines=['离线配置检查通过（不代表已连接后台）' if result.get('ready_for_readonly') else '还需要完成以下配置：']
                lines += ['• '+CHECK_LABELS.get(c,c) for c in result.get('blockers',[])]
                lines += ['提示：'+CHECK_LABELS.get(c,c) for c in result.get('warnings',[])]
                if not result:lines=['检查未完成，请检查本地安装或配置。']
                self.set_text(self.config_result,'\n'.join(lines));self.status.set('离线检查结束，未发起网络请求。')
            elif code==0 and result.get('job_id'):
                self.last_job_id=result['job_id'];self.refresh_jobs();self.jobs.selection_set(self.last_job_id);self.jobs.see(self.last_job_id);self.select_job()
                self.status.set('模拟任务结束：'+status_label(result.get('status')))
            else:self.status.set('模拟未完成。请查看任务状态和本地报告，不能视为成功。');self.refresh_jobs()
        except queue.Empty:pass
        if self.worker is not None:
            elapsed=int(time.monotonic()-self.started);self.status.set(('离线检查' if self.worker=='check' else '模拟运行')+'进行中 · '+str(elapsed)+' 秒')
            if self.worker=='fake':self.refresh_jobs()
        self.root.after(300,self.poll)

    def refresh_jobs(self):
        selected=self.jobs.selection();self.rows=list_jobs(self.data_directory)
        for item in self.jobs.get_children():self.jobs.delete(item)
        for row in self.rows:self.jobs.insert('', 'end', iid=row['job_id'], text=row['job_id'],values=(row['pid'] or '',row['shop'] or '',status_label(row['state'])))
        if selected and self.jobs.exists(selected[0]):self.jobs.selection_set(selected[0])

    def choose_data(self):
        if self.worker is not None:return
        selected=filedialog.askdirectory(title='选择独立任务数据目录',initialdir=str(self.data_directory))
        if selected:self.data_directory=Path(selected).resolve();self.data_text.set('数据目录：'+str(self.data_directory));self.refresh_jobs()

    def select_job(self,event=None):
        selection=self.jobs.selection()
        if not selection:return
        try:
            job=load_job(self.data_directory,selection[0]);summary=job['summary'] or {};state=job['state'].get('state')
            detail='状态：'+status_label(state)+'\n任务：'+selection[0]+'\n证据目录：'+job['path']
            if summary:detail+='\n模拟保存：'+str(summary.get('saves'))+' 次    模拟上传：'+str(summary.get('uploads'))+' 次    独立回读：'+str(summary.get('independent_readbacks',0))+' 次\n真实模型 / 线上写入：0 / 0'
            self.set_text(self.task_detail,detail);self.pairs=image_pairs(job['path'])
            labels=[str(i+1)+' · '+ACTION_LABELS.get(p['action'],p['action'])+' · '+('计划可执行' if p['decision']=='AUTO_SAFE' else '待复核') for i,p in enumerate(self.pairs)]
            self.pair_box['values']=labels
            if labels:self.pair_box.current(0);self.show_pair()
            else:self.pair_selection.set('');self.before_label.configure(image='',text='该任务没有图片变更记录');self.after_label.configure(image='',text='未生成处理后图片');self.photos=[]
        except (OSError,ValueError,TypeError):self.set_text(self.task_detail,'任务证据不完整或图片字节已变化，无法作为已验证结果展示。')

    def show_pair(self):
        index=self.pair_box.current()
        if not 0<=index<len(self.pairs):return
        pair=self.pairs[index];self.photos=[]
        for widget,path in ((self.before_label,pair['before']),(self.after_label,pair['after'])):
            if path:
                try:
                    with Image.open(path) as source:image=source.convert('RGB');image.thumbnail((470,440))
                    photo=ImageTk.PhotoImage(image);self.photos.append(photo);widget.configure(image=photo,text='')
                except (OSError,ValueError):widget.configure(image='',text='图片无法解码')
            else:widget.configure(image='',text='整图删除，无处理后图片' if pair['action']=='DELETE' else '尚无可显示的候选图')
        self.picture_note.set(ACTION_LABELS.get(pair['action'],pair['action'])+' · 图片已按任务记录校验字节 SHA，原始证据保持不变。')

    def close(self):
        if self.worker is not None:messagebox.showinfo('任务仍在运行','当前本地任务尚未结束，请完成后关闭窗口。');return
        self.root.destroy()

def main(config_directory=None,data_directory=None):
    root=tk.Tk();DesktopApp(root,config_directory,data_directory);root.mainloop()

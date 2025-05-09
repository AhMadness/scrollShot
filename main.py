import tkinter as tk, threading, time, os, sys, pyautogui, pyperclip
from tkinter import ttk, messagebox
from PIL import Image, ImageChops
from reportlab.pdfgen import canvas

# presets from your picture
SS_REGION, SS_SCROLL = (1066, 178, 726, 713), 686
OCR_REGION, OCR_SCROLL = (519, 145, 860, 871), 835
MOUSE_TOLERANCE, DEFAULT_NUM_SHOTS = 20, 10

def images_equal(a,b): return not ImageChops.difference(a,b).getbbox()
def next_desktop_name(base,ext):
    desk=os.path.join(os.path.expanduser('~'),'Desktop'); p=os.path.join(desk,base+ext); n=1
    while os.path.exists(p): p=os.path.join(desk,f'{base}{n}{ext}'); n+=1
    return p

class ScrollShotGUI:
    def __init__(self, root: tk.Tk):
        self.root=root; root.title('ScrollShot')
        w,h=400,360; sx,sy=root.winfo_screenwidth(),root.winfo_screenheight()
        root.geometry(f'{w}x{h}+{(sx-w)//2}+{(sy-h)//2-100}')
        root.configure(bg='#2e2e2e'); root.resizable(False,False)

        # state vars
        self.mode=tk.StringVar(value='ss')    # 'ss'|'ocr'
        self.dir =tk.StringVar(value='down')
        self.open=tk.BooleanVar(value=False)
        self.paused=self.stop=False
        self.save_partial=True
        self.temp_imgs=[]; self.txt_path=None
        self.last_img=None; self.last_txt=None
        self.default_region=SS_REGION

        self._build_ui()
        self._apply_defaults()   # show starting defaults

    # ─── UI ────────────────────────────────────────────
    def _build_ui(self):
        bg='#2e2e2e'
        f=tk.Frame(self.root,bg=bg); f.pack(expand=1,fill='both')
        f.bind('<ButtonPress-1>',self._win_down); f.bind('<B1-Motion>',self._win_drag)

        # mode selector (top)
        mfr=tk.Frame(f,bg=bg); mfr.pack(pady=6)
        for v,label in (('ss','Screenshot‑PDF'),('ocr','OCR‑TXT')):
            tk.Radiobutton(mfr,text=label,value=v,variable=self.mode,
                           bg=bg,fg='white',selectcolor=bg,
                           command=self._apply_defaults).pack(side='left',padx=6)

        tk.Button(f,text='Select Screenshot Region',command=self._pick_region,
                  bg='#444',fg='white',relief='flat').pack(pady=8)
        self.rlbl=tk.Label(f,text='',bg=bg,fg='white'); self.rlbl.pack()

        # num shots
        nfr=tk.Frame(f,bg=bg); nfr.pack(pady=2)
        tk.Label(nfr,text='Num Shots:',bg=bg,fg='white').pack(side='left',padx=5)
        self.num_e=tk.Entry(nfr,width=10,justify='center',bg='#555',fg='white',relief='flat')
        self.num_e.insert(0,'deadend'); self.num_e.pack(side='left')

        # scroll value
        sfr=tk.Frame(f,bg=bg); sfr.pack(pady=2)
        tk.Label(sfr,text='Scroll Value:',bg=bg,fg='white').pack(side='left',padx=5)
        self.sc_e=tk.Entry(sfr,width=10,justify='center',bg='#555',fg='white',relief='flat'); self.sc_e.pack(side='left')

        # scroll dir
        dfr=tk.Frame(f,bg=bg); dfr.pack(pady=3)
        tk.Label(dfr,text='Scroll Direction:',bg=bg,fg='white').pack(side='left',padx=5)
        for v,txt in (('down','Scroll Down'),('up','Scroll Up')):
            tk.Radiobutton(dfr,text=txt,value=v,variable=self.dir,
                           bg=bg,fg='white',selectcolor=bg).pack(side='left',padx=4)

        tk.Checkbutton(f,text='Open output after capture',variable=self.open,
                       bg=bg,fg='white',selectcolor=bg,activebackground=bg).pack(pady=4)

        # buttons
        bfr=tk.Frame(f,bg=bg); bfr.pack(pady=8)
        self.start=tk.Button(bfr,text='Start',width=10,bg='#444',fg='white',relief='flat',command=self._start)
        self.pause=tk.Button(bfr,text='Pause',width=10,bg='#444',fg='white',relief='flat',state='disabled',command=self._toggle)
        self.stopb=tk.Button (bfr,text='Stop', width=10,bg='#444',fg='white',relief='flat',state='disabled',command=self._stop)
        self.start.grid(row=0,column=0,padx=5)
        self.pause.grid(row=0,column=1,padx=5)
        self.stopb.grid (row=0,column=2,padx=5)

        # progress
        pfr=tk.Frame(f,bg=bg); pfr.pack(fill='x',padx=20,pady=12)
        self.pv=tk.DoubleVar()
        ttk.Style().configure('TProgressbar',troughcolor='#444',background='green')
        ttk.Progressbar(pfr,variable=self.pv,maximum=100).pack(fill='x')
        self.plbl=tk.Label(pfr,text='0/0',bg=bg,fg='white'); self.plbl.place(relx=.5,rely=.5,anchor='center')

    # window drag
    def _win_down(self,e): self._ox,self._oy=e.x_root-self.root.winfo_x(),e.y_root-self.root.winfo_y()
    def _win_drag(self,e): self.root.geometry(f'+{e.x_root-self._ox}+{e.y_root-self._oy}')

    # mode‑specific defaults
    def _apply_defaults(self):
        if self.mode.get()=='ocr':
            self.default_region, sv = OCR_REGION, OCR_SCROLL
        else:
            self.default_region, sv = SS_REGION, SS_SCROLL
        self.rlbl.config(text=f'Region: {self.default_region}')
        self.sc_e.delete(0,'end'); self.sc_e.insert(0,str(sv))

    # region picker
    def _pick_region(self):
        top=tk.Toplevel(self.root); top.attributes('-fullscreen',True); top.attributes('-alpha',0.3); top.config(bg='black')
        cv=tk.Canvas(top,cursor='cross',bg='gray'); cv.pack(expand=1,fill='both'); d={}
        def dn(e): d['sx'],d['sy']=e.x,e.y; d['rect']=cv.create_rectangle(e.x,e.y,e.x,e.y,outline='red',width=2)
        def dr(e): cv.coords(d['rect'],d['sx'],d['sy'],e.x,e.y)
        def up(e):
            x1,y1,x2,y2=min(d['sx'],e.x),min(d['sy'],e.y),max(d['sx'],e.x),max(d['sy'],e.y)
            self.default_region=(x1,y1,x2-x1,y2-y1); self.rlbl.config(text=f'Region: {self.default_region}'); top.destroy()
        cv.bind('<ButtonPress-1>',dn); cv.bind('<B1-Motion>',dr); cv.bind('<ButtonRelease-1>',up)

    # control buttons
    def _start(self):
        try: scroll=int(self.sc_e.get())
        except: scroll=SS_SCROLL
        shots=self.num_e.get().strip().lower()
        self.limit=float('inf') if shots=='deadend' else int(shots or DEFAULT_NUM_SHOTS)
        self.paused=self.stop=False; self.save_partial=True
        self.temp_imgs.clear(); self.txt_path=None
        self.last_img=self.last_txt=None
        self._update_prog(0)
        self.start.config(state='disabled'); self.pause.config(state='normal',text='Pause'); self.stopb.config(state='normal')
        threading.Thread(target=self._run,args=(scroll,),daemon=True).start()

    def _toggle(self):
        self.paused=not self.paused; self.pause.config(text='Resume' if self.paused else 'Pause')

    def _stop(self):
        ans=messagebox.askyesno('Stop Process','Save what has been captured so far?')
        self.save_partial=ans
        self.stop=True

    # worker thread
    def _run(self,scroll):
        time.sleep(3); anchor=pyautogui.position(); current=0
        while not self.stop and current<self.limit:
            if abs(pyautogui.position().x-anchor.x)>MOUSE_TOLERANCE or \
               abs(pyautogui.position().y-anchor.y)>MOUSE_TOLERANCE:
                self.paused=True; self.pause.config(text='Resume')
            while self.paused and not self.stop: time.sleep(.1)
            if self.stop: break

            dup=False
            if self.mode.get()=='ss':
                img=pyautogui.screenshot(region=self.default_region).convert('RGB')
                if self.limit==float('inf') and self.last_img and images_equal(img,self.last_img): dup=True
                else:
                    tmp=f'temp_{current}.png'; img.save(tmp); self.temp_imgs.append(tmp); self.last_img=img
            else:
                pyperclip.copy('')
                pyautogui.moveTo(*self.default_region[:2]); pyautogui.hotkey('ctrl','shift','o'); time.sleep(0.1)
                pyautogui.mouseDown()
                pyautogui.moveTo(self.default_region[0]+self.default_region[2],
                                 self.default_region[1]+self.default_region[3],duration=0.1)
                time.sleep(0.5); pyautogui.mouseUp()
                txt=''; t0=time.time()
                while time.time()-t0<15:
                    if self.stop: break
                    if self.paused: time.sleep(.1); continue
                    txt=pyperclip.paste()
                    if txt.strip(): break
                    time.sleep(.2)
                if self.stop: break
                is_dup = txt.strip() == (self.last_txt or '')
                if is_dup:  # identical to previous capture
                    dup = True  # signal loop‑exit
                else:  # unique → keep it
                    if self.txt_path is None:
                        self.txt_path = next_desktop_name('combined', '.txt')
                    with open(self.txt_path, 'a', encoding='utf-8') as f:
                        f.write(f'--- Page {current + 1} ---\n{txt.strip() or "[No text]"}\n\n')
                    self.last_txt = txt.strip()

            if dup: break
            current+=1; self._update_prog(current)

            if current<self.limit and not self.stop:
                pyautogui.moveTo(anchor)
                pyautogui.scroll(-scroll if self.dir.get()=='down' else scroll)
                time.sleep(.1)

        # wrap‑up
        if self.save_partial:
            if self.mode.get()=='ss' and self.temp_imgs:
                pdf=next_desktop_name('combined','.pdf'); self._pdf(pdf)
                if self.open.get(): self._open(pdf)
            elif self.mode.get()=='ocr' and self.txt_path and self.open.get():
                self._open(self.txt_path)
        else:
            # discard
            for p in self.temp_imgs: os.remove(p)
            if self.txt_path and os.path.exists(self.txt_path): os.remove(self.txt_path)

        # temp cleanup
        if self.mode.get()=='ss':
            for p in self.temp_imgs:
                if os.path.exists(p): os.remove(p)
        self.root.after(0,self._reset)

    # utils
    def _update_prog(self,val):
        pct=0 if self.limit==float('inf') else val/self.limit*100
        self.root.after(0,lambda: (self.pv.set(pct),
                                   self.plbl.config(text=f'{val}/{ "?" if self.limit==float("inf") else self.limit }')))

    def _pdf(self,path):
        h=sum(Image.open(p).height for p in self.temp_imgs)
        c=canvas.Canvas(path,pagesize=(self.default_region[2],h)); y=h
        for p in self.temp_imgs:
            img=Image.open(p); y-=img.height
            c.drawImage(p,0,y,width=img.width,height=img.height,mask='auto')
        c.save()

    def _open(self,p):
        if sys.platform.startswith('win'): os.startfile(p)
        elif sys.platform.startswith('darwin'): os.system(f'open "{p}"')
        else: os.system(f'xdg-open "{p}"')

    def _reset(self):
        self.start.config(state='normal'); self.pause.config(state='disabled',text='Pause'); self.stopb.config(state='disabled')
        self._update_prog(0)

    # drag helpers
    def _win_down(self,e): self._ox,self._oy=e.x_root-self.root.winfo_x(),e.y_root-self.root.winfo_y()
    def _win_drag(self,e): self.root.geometry(f'+{e.x_root-self._ox}+{e.y_root-self._oy}')

# ─── launch ────────────────────────────────────────────
if __name__=='__main__':
    ScrollShotGUI(tk.Tk()).root.mainloop()

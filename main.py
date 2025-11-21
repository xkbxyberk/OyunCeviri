import cv2
import pytesseract
import threading
import time
import tkinter as tk
import subprocess
import requests
from PIL import Image, ImageTk

# --- KULLANICI AYARLARI ---
DEEPL_API_KEY = "d99d73c5-7870-43bb-9f28-bb096d804452:fx"
TESSERACT_CMD_PATH = '/opt/homebrew/bin/tesseract'
# --------------------------

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD_PATH

class CeviriUygulamasi:
    def __init__(self):
        # Uyanık Kalma Modu
        self.uyku_engelleyici = subprocess.Popen(["caffeinate", "-d"])

        self.root = tk.Tk()
        self.root.withdraw() 
        
        self.roi_area = None
        self.camera_id = 0
        self.capture = None
        self.is_running = False
        self.is_paused = False # Yeniden seçim yaparken döngüyü durdurmak için

        try:
            if self.kamerayi_belirle():
                self.alani_sec()
                self.baslat_arayuz()
            else:
                self.cikis()
        except Exception as e:
            print(f"KRİTİK HATA: {e}")
            self.cikis()

    def kamerayi_belirle(self):
        print("Kamera aranıyor... Lütfen açılan pencereye odaklanın.")
        active_cam = 0
        while True:
            cap = cv2.VideoCapture(active_cam)
            if not cap.isOpened():
                active_cam = 0
                continue

            ret, frame = cap.read()
            if not ret:
                cap.release()
                active_cam += 1
                continue

            cv2.putText(frame, f"Kamera ID: {active_cam}", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            cv2.putText(frame, "Secmek icin: Y | Gecmek icin: N", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            
            cv2.imshow("Kamera Secimi", frame)
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('y'):
                self.camera_id = active_cam
                self.capture = cap
                cv2.destroyAllWindows()
                cv2.waitKey(1)
                return True
            elif key == ord('n'):
                cap.release()
                active_cam += 1
            elif key == 27:
                cap.release()
                cv2.destroyAllWindows()
                return False

    def alani_sec(self):
        # Kamerayı kontrol et
        if self.capture is None:
            return

        # Kameradan taze bir görüntü almak için buffer'ı temizle
        for _ in range(5): 
            self.capture.read()
        
        ret, frame = self.capture.read()
        if not ret:
            print("Görüntü alınamadı!")
            return

        print("Mouse ile alanı seçin ve ENTER'a basın.")
        
        # macOS pencere senkronizasyonu için bekleme
        time.sleep(0.5)
        
        # ROI Seçim Penceresi
        r = cv2.selectROI("Cevrilecek Alani Sec", frame, showCrosshair=True, fromCenter=False)
        cv2.destroyAllWindows()
        cv2.waitKey(1)
        
        # Eğer seçim yapılmadıysa varsayılan ata, yapıldıysa güncelle
        if r != (0, 0, 0, 0):
            self.roi_area = r

    def yeniden_secim_yap(self, event=None):
        """ 'R' tuşuna basıldığında çalışır. Arayüzü gizler, seçimi yaptırır, geri gelir. """
        print("Yeniden seçim başlatılıyor...")
        self.is_paused = True # Video döngüsünü duraklat
        
        self.root.withdraw() # Arayüzü gizle
        
        # OpenCV ve Tkinter çakışmasını önlemek için kısa bekleme
        self.root.update() 
        time.sleep(0.5)
        
        self.alani_sec() # Seçim fonksiyonunu çağır
        
        self.root.deiconify() # Arayüzü geri getir
        self.root.lift()
        self.root.attributes('-topmost',True)
        self.root.after_idle(self.root.attributes,'-topmost',False)
        
        self.is_paused = False # Döngüyü devam ettir
        print("Yeniden seçim tamamlandı.")

    def baslat_arayuz(self):
        self.root.deiconify()
        self.root.title("Oyun Çevirici")
        self.root.attributes("-fullscreen", True)
        self.root.configure(bg="black")
        
        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight()
        
        self.font_tr = ("Arial", 56, "bold")
        self.font_en = ("Courier New", 36, "italic")
        self.color_tr = "#FFD700"
        self.color_en = "#A9A9A9"

        self.frame_top = tk.Frame(self.root, bg="black", height=self.screen_height//2, width=self.screen_width)
        self.frame_top.pack(side="top", fill="both", expand=True)
        self.frame_top.pack_propagate(False)

        self.frame_bottom = tk.Frame(self.root, bg="black", height=self.screen_height//2, width=self.screen_width)
        self.frame_bottom.pack(side="bottom", fill="both", expand=True)
        self.frame_bottom.pack_propagate(False)

        self.lbl_tr = tk.Label(self.frame_top, text="Çeviri Başlıyor...\nYeniden seçim için 'R' tuşuna basın", font=self.font_tr, fg=self.color_tr, bg="black", 
                               wraplength=self.screen_width-100, justify="center")
        self.lbl_tr.place(relx=0.5, rely=0.5, anchor="center")

        self.lbl_en = tk.Label(self.frame_bottom, text="Waiting for subtitles...", font=self.font_en, fg=self.color_en, bg="black", 
                               wraplength=self.screen_width-100, justify="center")
        self.lbl_en.place(relx=0.5, rely=0.5, anchor="center")

        self.separator = tk.Frame(self.root, height=5, bd=0, relief="sunken", bg="#303030")
        self.separator.place(relx=0.5, rely=0.5, anchor="center", relwidth=1)
        
        self.is_running = True
        
        self.thread = threading.Thread(target=self.video_isleme_dongusu)
        self.thread.daemon = True
        self.thread.start()
        
        # KLAVYE KISAYOLLARI
        self.root.bind("<Escape>", self.cikis)
        self.root.bind("r", self.yeniden_secim_yap) # Küçük r
        self.root.bind("R", self.yeniden_secim_yap) # Büyük R (Caps Lock açıksa)

        self.root.lift()
        self.root.attributes('-topmost',True)
        self.root.after_idle(self.root.attributes,'-topmost',False)
        
        self.root.mainloop()

    def cevir_deepl(self, text):
        if not text or len(text) < 3:
            return ""
        try:
            url = "https://api-free.deepl.com/v2/translate"
            data = {
                "auth_key": DEEPL_API_KEY,
                "text": text,
                "target_lang": "TR"
            }
            response = requests.post(url, data=data)
            
            if response.status_code == 403:
                return "API Key Hatalı"
            if response.status_code == 456:
                return "Kota Doldu"
                
            result = response.json()
            if 'translations' in result:
                return result['translations'][0]['text']
            else:
                return "Çeviri Hatası"
        except Exception:
            return "Bağlantı Yok"

    def video_isleme_dongusu(self):
        last_text = ""
        
        while self.is_running:
            # Eğer seçim yapılıyorsa (paused), döngüyü beklet
            if self.is_paused:
                time.sleep(0.5)
                continue

            if self.capture is None or not self.capture.isOpened():
                break
                
            ret, frame = self.capture.read()
            if not ret:
                time.sleep(1)
                continue

            # ROI alanı henüz belirlenmemişse bekle
            if self.roi_area is None:
                time.sleep(1)
                continue

            x, y, w, h = self.roi_area
            # Güvenlik kontrolü
            if w == 0 or h == 0:
                continue

            # 1. Alanı Kes
            crop_img = frame[y:y+h, x:x+w]
            
            # 2. Görüntüyü Büyüt (Upscale) - Okumayı İnanılmaz Artırır
            # Görüntüyü 3 katına çıkarıyoruz ki harfler netleşsin
            scale_percent = 300 # Yüzde 300
            width = int(crop_img.shape[1] * scale_percent / 100)
            height = int(crop_img.shape[0] * scale_percent / 100)
            dim = (width, height)
            
            try:
                resized = cv2.resize(crop_img, dim, interpolation = cv2.INTER_CUBIC)

                # 3. Siyah-Beyaz Yap ve İşle
                gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
                
                # Ters çevir (Beyaz yazıyı Siyah yap) - Tesseract siyah harfleri daha iyi okur
                gray = cv2.bitwise_not(gray)
                
                # Threshold (Eşikleme) - Gri tonları at, sadece Siyah ve Beyaz kalsın
                _, thresh = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY)

                # --- DÜZELTME: cv2.imshow ve waitKey satırlarını kaldırdık ---
                # macOS'te thread içinde pencere açmak yasaktır, hatanın sebebi buydu.
                # Ama yukarıdaki iyileştirmeler (resize, threshold) hala çalışıyor!
                # -------------------------------------------------------------

                # 4. OCR İşlemi
                custom_config = r'--oem 3 --psm 6'
                text = pytesseract.image_to_string(thresh, lang='eng', config=custom_config)
                clean_text = " ".join(text.split())
                
                # Temizlik
                ignores = ["|", "©", "®", "{", "}", "[", "]"]
                for char in ignores:
                    clean_text = clean_text.replace(char, "")

                if len(clean_text) > 3 and clean_text != last_text:
                    print(f"Okunan: {clean_text}")
                    translated = self.cevir_deepl(clean_text)
                    self.root.after(0, self.guncelle_arayuz, translated, clean_text)
                    last_text = clean_text
            
            except Exception as e:
                print(f"Görüntü işleme hatası: {e}")
                continue
            
            time.sleep(1.0)

    def guncelle_arayuz(self, tr_text, en_text):
        self.lbl_tr.config(text=tr_text)
        self.lbl_en.config(text=en_text)

    def cikis(self, event=None):
        self.is_running = False
        if self.capture:
            self.capture.release()
        if hasattr(self, 'uyku_engelleyici'):
            self.uyku_engelleyici.terminate()
        if hasattr(self, 'root'):
             self.root.destroy()

if __name__ == "__main__":
    app = CeviriUygulamasi()
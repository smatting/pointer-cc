# https://stackoverflow.com/questions/84847/how-do-i-create-a-self-signed-certificate-for-code-signing-on-windows

makecert -r -pe -n "CN=Stefan Matting CA" -ss CA -sr CurrentUser -a sha256 -cy authority -sky signature -sv StefanMattingCA.pvk StefanMattingCA.cer

makecert -pe -n "CN=Stefan Matting SPC" -a sha256 -cy end `
         -sky signature `
         -ic StefanMattingCA.cer -iv StefanMattingCA.pvk `
         -sv StefanMattingSPC.pvk StefanMattingSPC.cer

pvk2pfx -pvk StefanMattingSPC.pvk -spc StefanMattingSPC.cer -pfx StefanMattingSPC.pfx

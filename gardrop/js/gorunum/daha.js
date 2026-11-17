// Diğer bölümler menüsü.
export const baslik = "Diğer";

export async function ciz(kok) {
  const b = (href, ad, alt) => `<a href="${href}"><span>${ad}<small>${alt}</small></span><span class="soluk">›</span></a>`;
  kok.innerHTML = `<div class="menu-liste">
    ${b("#/alisveris", "Alışveriş", "İstek listesi, almadan önce test, eksikler, elden çıkarma")}
    ${b("#/seyahat", "Seyahat bavulu", "Gün gün kombin planı ve bavul listesi")}
    ${b("#/kapsul", "Kapsül gardrop", "Az parçayla çok kombin")}
    ${b("#/ekle", "Parça ekle", "Fotoğraf, toplu ekleme, link")}
    ${b("#/ayarlar", "Ayarlar", "Şehir, profiller, yedekleme, bulut senkron")}
  </div>`;
}

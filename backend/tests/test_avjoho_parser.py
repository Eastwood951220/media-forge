from backend.app.modules.content.actresses.avjoho_parser import parse_avjoho_profile


SAMPLE = """
<div id="main">
  <h1 class="entry-title">宮上唯依花（みやうえゆいか）</h1>
  <div id="the-content" class="entry-content">
    <div class="database">
      <div class="gazou"><a href="https://example.test/work"><img src="https://pics.dmm.co.jp/digital/video/1dldss00528/1dldss00528ps.jpg" alt="宮上唯依花"></a></div>
      <div class="profile"><table><tbody>
        <tr><th>デビュー</th><td>2026年9月3日</td></tr>
        <tr><th>生年月日</th><td>1977年12月1日</td></tr>
        <tr><th>身長</th><td>163cm</td></tr>
        <tr><th>スリーサイズ</th><td>B90cm W62cm H93cm</td></tr>
        <tr><th>カップ</th><td>E</td></tr>
      </tbody></table></div>
      <div class="birthplace"><table><tbody><tr><th>出身地</th><td>京都府</td></tr></tbody></table></div>
      <div class="blood-type"><table><tbody><tr><th>血液型</th><td>A型</td></tr></tbody></table></div>
      <div class="shumi-tokugi"><table><tbody><tr><th>趣味・特技</th><td>神社・美術館巡り<br>ヨガ</td></tr></tbody></table></div>
      <div class="profile2">2026年にDAHLIAから48歳としてデビュー。</div>
      <div class="name"><table><tbody><tr><th>別名</th><td>–</td></tr></tbody></table></div>
      <div class="maker"><table><tbody><tr><th>専属メーカー</th><td>DAHLIA ※デビュー</td></tr></tbody></table></div>
      <div class="sns"><table><tbody><tr><th>X（旧Twitter）</th><td><a href="https://x.com/MiyaueYuika">@MiyaueYuika</a></td></tr></tbody></table></div>
      <h2>主な出演作品</h2>
      <p><span class="gazou-large"><a href="https://example.test/work"><img src="https://pics.dmm.co.jp/digital/video/1dldss00528/1dldss00528pl.jpg" alt="作品画像"></a></span><br>
      <span class="text-link"><a href="https://example.test/work">宮上唯依花 Debut</a></span></p>
    </div>
    <div class="yarpp-thumbnails-horizontal">
      <a class="yarpp-thumbnail" href="https://db.avjoho.com/example/" title="永峰椿（ながみねつばき）">
        <img src="https://db.avjoho.com/wp-content/uploads/sample.jpg" alt="永峰椿">
        <span class="yarpp-thumbnail-title">永峰椿（ながみねつばき）</span>
      </a>
    </div>
  </div>
</div>
"""


def test_parse_avjoho_profile_extracts_profile_fields() -> None:
    profile = parse_avjoho_profile(SAMPLE, "https://db.avjoho.com/宮上唯依花/")

    assert profile is not None
    assert profile.display_name == "宮上唯依花"
    assert profile.reading == "みやうえゆいか"
    assert profile.image_url.endswith("1dldss00528ps.jpg")
    assert profile.debut_date.isoformat() == "2026-09-03"
    assert profile.birth_date.isoformat() == "1977-12-01"
    assert profile.height_cm == 163
    assert profile.bust_cm == 90
    assert profile.waist_cm == 62
    assert profile.hip_cm == 93
    assert profile.cup == "E"
    assert profile.birthplace == "京都府"
    assert profile.blood_type == "A型"
    assert "ヨガ" in profile.hobbies
    assert profile.exclusive_maker == "DAHLIA ※デビュー"
    assert profile.sns_links == [{"label": "X（旧Twitter）", "url": "https://x.com/MiyaueYuika", "text": "@MiyaueYuika"}]
    assert profile.representative_works[0]["title"] == "宮上唯依花 Debut"
    assert profile.similar_actresses[0]["name"] == "永峰椿（ながみねつばき）"

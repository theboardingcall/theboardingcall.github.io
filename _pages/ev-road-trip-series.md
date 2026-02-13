---
title: "The Great EV Road Trip 2023"
permalink: /ev-road-trip-series/
layout: single
classes: wide
header:
  overlay_image: /assets/images/2023/06/Screenshot-2023-06-20-at-10.01.59-PM.png
  overlay_filter: 0.5
  caption: "3,000 miles across the Western United States"
image: /assets/images/2023/06/Screenshot-2023-06-20-at-10.01.59-PM.png
description: "Follow our 27-day, 3,000-mile EV road trip through the Western US with daily photo journals, charging tips, and national park guides."
---

<div class="series-landing-hero">
  <div class="series-stats">
    <div class="stat-item">
      <span class="stat-number">27</span>
      <span class="stat-label">Days</span>
    </div>
    <div class="stat-item">
      <span class="stat-number">3,000</span>
      <span class="stat-label">Miles</span>
    </div>
    <div class="stat-item">
      <span class="stat-number">7</span>
      <span class="stat-label">States</span>
    </div>
    <div class="stat-item">
      <span class="stat-number">5</span>
      <span class="stat-label">National Parks</span>
    </div>
  </div>
</div>

## The Journey

In June 2023, we embarked on an epic 27-day electric vehicle road trip through the Western United States. From the Pacific Northwest through Idaho, Utah's mighty five national parks, and ending in the desert heat of Las Vegas, this journey proved that EV road trips are not only possible—they're incredible.

Follow along as we navigate charging networks, capture stunning landscapes with drone photography, and discover hidden gems across seven states. Each post includes practical EV charging information, photography tips, and travel recommendations.

## The Route

Our journey took us through some of America's most breathtaking landscapes:

- **Pacific Northwest**: Starting from home through Washington's wine country
- **Idaho**: Boise's urban trails and Twin Falls' dramatic canyons
- **Utah**: Salt Lake City, Provo, and the mighty five national parks
- **Nevada**: Ending in the desert oasis of Las Vegas

## All Posts in This Series

<div class="series-grid">
{% assign series = site.data.ev_road_trip %}
{% for post in series %}
  {% assign post_data = site.posts | where: "permalink", post.url | first %}
  {% if post_data %}
  <div class="series-card">
    {% if post_data.header.image %}
    <div class="series-card__image">
      <a href="{{ post.url }}">
        <img src="{{ post_data.header.image }}" alt="{{ post.title }}">
      </a>
    </div>
    {% endif %}
    <div class="series-card__content">
      <h3 class="series-card__title">
        <a href="{{ post.url }}">{{ post.title }}</a>
      </h3>
      {% if post_data.excerpt %}
      <p class="series-card__excerpt">{{ post_data.excerpt | strip_html | truncate: 120 }}</p>
      {% endif %}
      <a href="{{ post.url }}" class="series-card__cta">Read Post →</a>
    </div>
  </div>
  {% endif %}
{% endfor %}
</div>

## EV Road Trip Tips

Based on our 3,000-mile journey, here are our top recommendations for planning an EV road trip:

### Charging Strategy
- **Plan charging stops around meals and activities**: We charged at hotels overnight, during lunch breaks, and at destinations
- **Download all charging network apps ahead of time**: Tesla Supercharger, Electrify America, ChargePoint, and EVgo
- **Budget extra time for charging in remote areas**: Some chargers were slower than expected or occupied

### Route Planning
- **National parks are EV-friendly**: Most had charging infrastructure nearby (Bryce Canyon City, Zion, etc.)
- **Utah is surprisingly well-equipped**: Salt Lake City to Zion corridor has excellent charging coverage
- **Summer heat affects range**: We saw 15-20% range reduction in 110°F+ desert temperatures

### Photography Gear
We captured this entire journey with:
- DJI drone for aerial landscape shots
- Mirrorless camera for low-light and Milky Way photography
- iPhone for quick snapshots and video

---

<div class="series-cta">
  <h2>Ready to Start the Journey?</h2>
  <p>Begin with Day 0 where we share our route planning and preparation.</p>
  <a href="/the-great-ev-road-trip-2023-day-0/" class="btn btn--primary btn--large">Start Reading →</a>
</div>

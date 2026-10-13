import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Sparkles, Eye, EyeOff, Zap, Activity, Waves } from 'lucide-react';

export type BackgroundMode = 'constellation' | 'stream' | 'ambient';
export type ParticleIntensity = 'subtle' | 'balanced' | 'dynamic';

interface InteractiveBackgroundProps {
  variant?: 'light' | 'dark' | 'adaptive';
  className?: string;
  showControls?: boolean;
}

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  baseRadius: number;
  radius: number;
  color: string;
  alpha: number;
  baseAlpha: number;
  pulseSpeed: number;
  pulseOffset: number;
}

interface Ripple {
  x: number;
  y: number;
  radius: number;
  maxRadius: number;
  alpha: number;
  speed: number;
}

export const InteractiveBackground: React.FC<InteractiveBackgroundProps> = ({
  variant = 'adaptive',
  className = '',
  showControls = true,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // User configuration states (persisted in localStorage)
  const [enabled, setEnabled] = useState<boolean>(() => {
    try {
      const saved = localStorage.getItem('dataops_bg_enabled');
      return saved !== null ? JSON.parse(saved) : true;
    } catch {
      return true;
    }
  });

  const [mode, setMode] = useState<BackgroundMode>(() => {
    try {
      return (localStorage.getItem('dataops_bg_mode') as BackgroundMode) || 'constellation';
    } catch {
      return 'constellation';
    }
  });

  const [intensity, setIntensity] = useState<ParticleIntensity>(() => {
    try {
      return (localStorage.getItem('dataops_bg_intensity') as ParticleIntensity) || 'balanced';
    } catch {
      return 'balanced';
    }
  });

  const [isWidgetOpen, setIsWidgetOpen] = useState(false);

  // Mouse & interaction states
  const mouseRef = useRef<{ x: number; y: number; isOver: boolean }>({
    x: -9999,
    y: -9999,
    isOver: false,
  });

  const particlesRef = useRef<Particle[]>([]);
  const ripplesRef = useRef<Ripple[]>([]);
  const animFrameIdRef = useRef<number | null>(null);

  // Save settings
  useEffect(() => {
    try {
      localStorage.setItem('dataops_bg_enabled', JSON.stringify(enabled));
      localStorage.setItem('dataops_bg_mode', mode);
      localStorage.setItem('dataops_bg_intensity', intensity);
    } catch (e) {
      console.warn('Could not persist background preferences', e);
    }
  }, [enabled, mode, intensity]);

  // Color palette selection based on variant
  const getPalette = useCallback(() => {
    if (variant === 'dark') {
      return {
        particles: ['#10B981', '#34D399', '#38BDF8', '#818CF8', '#A7F3D0'],
        connection: 'rgba(52, 211, 153, ',
        mouseConnection: 'rgba(56, 189, 248, ',
        glow: 'rgba(16, 185, 129, 0.15)',
        blob1: 'rgba(16, 185, 129, 0.12)',
        blob2: 'rgba(56, 189, 248, 0.10)',
        blob3: 'rgba(99, 102, 241, 0.08)',
      };
    }
    // Default / Light palette (sleek tech slate, emerald and electric blue)
    return {
      particles: ['#2D4351', '#10B981', '#0284C7', '#6366F1', '#475569'],
      connection: 'rgba(45, 67, 81, ',
      mouseConnection: 'rgba(16, 185, 129, ',
      glow: 'rgba(45, 67, 81, 0.08)',
      blob1: 'rgba(16, 185, 129, 0.08)',
      blob2: 'rgba(56, 189, 248, 0.07)',
      blob3: 'rgba(99, 102, 241, 0.05)',
    };
  }, [variant]);

  // Particle count resolver
  const getParticleCount = useCallback(
    (width: number, height: number) => {
      const area = width * height;
      const base = Math.min(Math.floor(area / 16000), 90);
      switch (intensity) {
        case 'subtle':
          return Math.max(20, Math.floor(base * 0.55));
        case 'dynamic':
          return Math.min(130, Math.floor(base * 1.45));
        case 'balanced':
        default:
          return Math.max(35, base);
      }
    },
    [intensity]
  );

  // Initialize particles
  const initParticles = useCallback(
    (width: number, height: number) => {
      const palette = getPalette();
      const count = getParticleCount(width, height);
      const particles: Particle[] = [];

      for (let i = 0; i < count; i++) {
        const speedMultiplier = intensity === 'dynamic' ? 1.4 : intensity === 'subtle' ? 0.6 : 1.0;
        let vx = (Math.random() - 0.5) * 0.9 * speedMultiplier;
        let vy = (Math.random() - 0.5) * 0.9 * speedMultiplier;

        if (mode === 'stream') {
          vx = (0.4 + Math.random() * 0.9) * speedMultiplier;
          vy = (0.2 + Math.random() * 0.5) * speedMultiplier;
        }

        const baseRadius = 1.6 + Math.random() * 2.2;
        const color = palette.particles[Math.floor(Math.random() * palette.particles.length)];
        const baseAlpha = 0.25 + Math.random() * 0.45;

        particles.push({
          x: Math.random() * width,
          y: Math.random() * height,
          vx,
          vy,
          baseRadius,
          radius: baseRadius,
          color,
          alpha: baseAlpha,
          baseAlpha,
          pulseSpeed: 0.02 + Math.random() * 0.03,
          pulseOffset: Math.random() * Math.PI * 2,
        });
      }

      particlesRef.current = particles;
    },
    [getPalette, getParticleCount, intensity, mode]
  );

  // Main canvas animation loop
  useEffect(() => {
    if (!enabled) {
      if (animFrameIdRef.current) {
        cancelAnimationFrame(animFrameIdRef.current);
      }
      return;
    }

    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d', { alpha: true });
    if (!ctx) return;

    let width = 0;
    let height = 0;
    let dpr = 1;

    const resize = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = window.innerWidth;
      height = window.innerHeight;

      canvas.width = width * dpr;
      canvas.height = height * dpr;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;

      ctx.scale(dpr, dpr);
      initParticles(width, height);
    };

    resize();
    window.addEventListener('resize', resize);

    // Global mouse tracking so interaction continues smoothly over components
    const handleMouseMove = (e: MouseEvent) => {
      mouseRef.current.x = e.clientX;
      mouseRef.current.y = e.clientY;
      mouseRef.current.isOver = true;
    };

    const handleMouseLeave = () => {
      mouseRef.current.isOver = false;
      mouseRef.current.x = -9999;
      mouseRef.current.y = -9999;
    };

    const handleClick = (e: MouseEvent) => {
      // Add interactive shockwave ripple
      ripplesRef.current.push({
        x: e.clientX,
        y: e.clientY,
        radius: 4,
        maxRadius: 180,
        alpha: 0.7,
        speed: 4.5,
      });

      // Give a gentle impulse to particles near click point
      const clickX = e.clientX;
      const clickY = e.clientY;
      particlesRef.current.forEach((p) => {
        const dx = p.x - clickX;
        const dy = p.y - clickY;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 200 && dist > 1) {
          const force = (1 - dist / 200) * 4;
          p.vx += (dx / dist) * force;
          p.vy += (dy / dist) * force;
        }
      });
    };

    window.addEventListener('mousemove', handleMouseMove, { passive: true });
    window.addEventListener('mouseleave', handleMouseLeave);
    window.addEventListener('click', handleClick, { passive: true });

    let step = 0;

    const render = () => {
      step += 1;
      ctx.clearRect(0, 0, width, height);

      const palette = getPalette();
      const mouse = mouseRef.current;
      const particles = particlesRef.current;
      const connectionDist = mode === 'constellation' ? 125 : 85;
      const mouseRadius = 150;

      // Update & Draw Ripples
      for (let r = ripplesRef.current.length - 1; r >= 0; r--) {
        const ripple = ripplesRef.current[r];
        ripple.radius += ripple.speed;
        ripple.alpha *= 0.94;

        if (ripple.alpha > 0.01 && ripple.radius < ripple.maxRadius) {
          ctx.beginPath();
          ctx.arc(ripple.x, ripple.y, ripple.radius, 0, Math.PI * 2);
          ctx.strokeStyle = `rgba(16, 185, 129, ${ripple.alpha * 0.6})`;
          ctx.lineWidth = 1.8;
          ctx.stroke();

          // Second subtle outer echo ring
          ctx.beginPath();
          ctx.arc(ripple.x, ripple.y, ripple.radius * 0.7, 0, Math.PI * 2);
          ctx.strokeStyle = `rgba(56, 189, 248, ${ripple.alpha * 0.4})`;
          ctx.lineWidth = 1;
          ctx.stroke();
        } else {
          ripplesRef.current.splice(r, 1);
        }
      }

      // Update and Draw Particles
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];

        // Soft pulsing glow
        const pulse = Math.sin(step * p.pulseSpeed + p.pulseOffset);
        p.alpha = Math.max(0.1, p.baseAlpha + pulse * 0.15);

        // Natural movement
        p.x += p.vx;
        p.y += p.vy;

        // Damping if accelerated by mouse/ripple
        p.vx *= 0.985;
        p.vy *= 0.985;

        // Ensure minimum motion
        if (Math.abs(p.vx) < 0.15) p.vx += (Math.random() - 0.5) * 0.2;
        if (Math.abs(p.vy) < 0.15) p.vy += (Math.random() - 0.5) * 0.2;

        // Screen boundary wrap
        if (p.x < -20) p.x = width + 20;
        if (p.x > width + 20) p.x = -20;
        if (p.y < -20) p.y = height + 20;
        if (p.y > height + 20) p.y = -20;

        // Interactive Mouse Attraction/Repulsion
        if (mouse.isOver) {
          const dx = mouse.x - p.x;
          const dy = mouse.y - p.y;
          const dist = Math.sqrt(dx * dx + dy * dy);

          if (dist < mouseRadius && dist > 1) {
            // Interactive mouse tether line
            const tetherAlpha = (1 - dist / mouseRadius) * 0.5;
            ctx.beginPath();
            ctx.moveTo(p.x, p.y);
            ctx.lineTo(mouse.x, mouse.y);
            ctx.strokeStyle = `${palette.mouseConnection}${tetherAlpha})`;
            ctx.lineWidth = 1.2;
            ctx.stroke();

            // Subtle gentle repulsion away from cursor to feel elastic
            const force = (1 - dist / mouseRadius) * 0.6;
            p.vx -= (dx / dist) * force;
            p.vy -= (dy / dist) * force;
            p.radius = p.baseRadius * 1.35;
          } else {
            p.radius = p.baseRadius;
          }
        }

        // Particle-to-Particle connections (Network mesh / Constellation)
        if (mode === 'constellation' || mode === 'stream') {
          for (let j = i + 1; j < particles.length; j++) {
            const p2 = particles[j];
            const dx = p.x - p2.x;
            const dy = p.y - p2.y;
            const dist = Math.sqrt(dx * dx + dy * dy);

            if (dist < connectionDist) {
              const lineAlpha = (1 - dist / connectionDist) * 0.22;
              ctx.beginPath();
              ctx.moveTo(p.x, p.y);
              ctx.lineTo(p2.x, p2.y);
              ctx.strokeStyle = `${palette.connection}${lineAlpha})`;
              ctx.lineWidth = 0.85;
              ctx.stroke();
            }
          }
        }

        // Draw particle node with subtle halo
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
        ctx.fillStyle = p.color;
        ctx.globalAlpha = p.alpha;
        ctx.fill();

        // Extra soft outer glow for larger particles
        if (p.baseRadius > 2.6) {
          ctx.beginPath();
          ctx.arc(p.x, p.y, p.radius * 2.2, 0, Math.PI * 2);
          ctx.fillStyle = p.color;
          ctx.globalAlpha = p.alpha * 0.18;
          ctx.fill();
        }

        ctx.globalAlpha = 1.0;
      }

      // Draw subtle interactive cursor halo when hovering
      if (mouse.isOver) {
        const gradient = ctx.createRadialGradient(
          mouse.x,
          mouse.y,
          0,
          mouse.x,
          mouse.y,
          mouseRadius * 0.8
        );
        gradient.addColorStop(0, 'rgba(16, 185, 129, 0.08)');
        gradient.addColorStop(0.5, 'rgba(56, 189, 248, 0.03)');
        gradient.addColorStop(1, 'rgba(0, 0, 0, 0)');

        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(mouse.x, mouse.y, mouseRadius * 0.8, 0, Math.PI * 2);
        ctx.fill();
      }

      animFrameIdRef.current = requestAnimationFrame(render);
    };

    animFrameIdRef.current = requestAnimationFrame(render);

    return () => {
      window.removeEventListener('resize', resize);
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseleave', handleMouseLeave);
      window.removeEventListener('click', handleClick);
      if (animFrameIdRef.current) {
        cancelAnimationFrame(animFrameIdRef.current);
      }
    };
  }, [enabled, initParticles, mode, intensity, getPalette]);

  const palette = getPalette();

  return (
    <div
      ref={containerRef}
      className={`fixed inset-0 pointer-events-none overflow-hidden select-none -z-10 ${className}`}
      aria-hidden="true"
    >
      {/* Dynamic Animated Ambient Aurora Blobs */}
      {enabled && (
        <div className="absolute inset-0 overflow-hidden pointer-events-none opacity-85">
          <div
            className="absolute -top-32 -left-32 w-[34rem] h-[34rem] rounded-full blur-[110px] animate-pulse"
            style={{
              background: palette.blob1,
              animationDuration: '10s',
            }}
          />
          <div
            className="absolute top-1/3 -right-24 w-[38rem] h-[38rem] rounded-full blur-[130px] animate-pulse"
            style={{
              background: palette.blob2,
              animationDuration: '14s',
              animationDelay: '3s',
            }}
          />
          <div
            className="absolute -bottom-32 left-1/4 w-[32rem] h-[32rem] rounded-full blur-[120px] animate-pulse"
            style={{
              background: palette.blob3,
              animationDuration: '12s',
              animationDelay: '6s',
            }}
          />

          {/* Minimal Matrix Dot Pattern for Tech/Scraper Intelligence Look */}
          <div
            className="absolute inset-0 opacity-[0.035]"
            style={{
              backgroundImage:
                'radial-gradient(circle at 1px 1px, currentColor 1px, transparent 0)',
              backgroundSize: '32px 32px',
            }}
          />
        </div>
      )}

      {/* Interactive HTML5 Particle Canvas */}
      <canvas
        ref={canvasRef}
        className="absolute inset-0 w-full h-full pointer-events-none"
      />

      {/* Floating Interactive Control Widget (Pointer Events Enabled on Widget itself) */}
      {showControls && (
        <div className="fixed bottom-4 right-4 pointer-events-auto z-40">
          {isWidgetOpen ? (
            <div className="bg-white/95 backdrop-blur-md border border-gray-200/90 rounded-2xl shadow-dropdown p-3.5 w-72 text-gray-800 transition-all duration-200 animate-in fade-in slide-in-from-bottom-2">
              <div className="flex items-center justify-between pb-2.5 mb-2.5 border-b border-gray-100">
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 rounded-lg bg-[#2D4351] text-white flex items-center justify-center">
                    <Sparkles className="w-3.5 h-3.5 text-green-400" />
                  </div>
                  <div>
                    <h4 className="text-xs font-bold text-gray-900 leading-tight">
                      Dynamic Visuals
                    </h4>
                    <span className="text-[10px] text-gray-500">
                      Interactive Particle Engine
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setEnabled(!enabled)}
                    title={enabled ? 'Disable Particles' : 'Enable Particles'}
                    className={`p-1.5 rounded-lg text-xs transition-colors ${
                      enabled
                        ? 'bg-white text-green-600 border border-green-200 hover:bg-green-50 dark:bg-black dark:text-green-500 dark:border-green-800 dark:hover:bg-green-900/30'
                        : 'bg-gray-100 text-gray-500 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700'
                    }`}
                  >
                    {enabled ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
                  </button>
                  <button
                    onClick={() => setIsWidgetOpen(false)}
                    className="p-1 rounded-md text-gray-400 hover:text-gray-600 hover:bg-gray-100 text-xs"
                    title="Close"
                  >
                    ✕
                  </button>
                </div>
              </div>

              {enabled && (
                <div className="space-y-3">
                  {/* Mode Selector */}
                  <div>
                    <label className="text-[10px] font-bold text-gray-500 uppercase tracking-wider block mb-1.5">
                      Animation Pattern
                    </label>
                    <div className="grid grid-cols-3 gap-1.5">
                      {[
                        { id: 'constellation', label: 'Neural', icon: Activity },
                        { id: 'stream', label: 'Flow', icon: Waves },
                        { id: 'ambient', label: 'Cosmic', icon: Zap },
                      ].map((item) => {
                        const Icon = item.icon;
                        const isSelected = mode === item.id;
                        return (
                          <button
                            key={item.id}
                            onClick={() => setMode(item.id as BackgroundMode)}
                            className={`flex flex-col items-center justify-center py-2 px-1 rounded-lg text-[10px] font-medium transition-all ${
                              isSelected
                                ? 'bg-[#2D4351] text-white shadow-sm'
                                : 'bg-gray-50 text-gray-700 hover:bg-gray-100 border border-gray-100'
                            }`}
                          >
                            <Icon className="w-3.5 h-3.5 mb-1" />
                            <span>{item.label}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  {/* Intensity Selector */}
                  <div>
                    <label className="text-[10px] font-bold text-gray-500 uppercase tracking-wider block mb-1.5">
                      Particle Density
                    </label>
                    <div className="grid grid-cols-3 gap-1.5">
                      {(['subtle', 'balanced', 'dynamic'] as ParticleIntensity[]).map((level) => {
                        const isSelected = intensity === level;
                        return (
                          <button
                            key={level}
                            onClick={() => setIntensity(level)}
                            className={`py-1 px-2 rounded-md text-[10px] font-medium capitalize transition-all ${
                              isSelected
                                ? 'bg-green-600 text-white font-semibold shadow-xs'
                                : 'bg-gray-50 text-gray-600 hover:bg-gray-100 border border-gray-100'
                            }`}
                          >
                            {level}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div className="pt-1 text-[10px] text-gray-400 flex items-center justify-between">
                    <span>💡 Move mouse or click to pulse</span>
                    <span className="text-green-600 font-medium">Live GPU</span>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <button
              onClick={() => setIsWidgetOpen(true)}
              className="group flex items-center gap-2 px-3 py-2 rounded-full bg-white/90 hover:bg-white text-gray-700 border border-gray-200/90 shadow-card hover:shadow-dropdown backdrop-blur-md transition-all duration-200 text-xs font-medium"
              title="Customize Dynamic Background"
            >
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-600 dark:bg-green-500"></span>
              </span>
              <Sparkles className="w-3.5 h-3.5 text-green-600 dark:text-green-500 group-hover:rotate-12 transition-transform" />
              <span className="text-[11px] font-semibold text-gray-800 hidden sm:inline">
                Interactive FX
              </span>
            </button>
          )}
        </div>
      )}
    </div>
  );
};

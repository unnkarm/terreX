"use client";

import { useEffect, useRef } from "react";

export default function Globe3D() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const rotRef = useRef({ x: 0.3, y: 0.6 });
  const mouseRef = useRef({ isDragging: false, lastX: 0, lastY: 0 });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animationFrameId: number;
    let width = (canvas.width = canvas.parentElement?.clientWidth || 550);
    let height = (canvas.height = canvas.parentElement?.clientHeight || 550);

    const handleResize = () => {
      if (!canvas || !canvas.parentElement) return;
      width = canvas.width = canvas.parentElement.clientWidth;
      height = canvas.height = canvas.parentElement.clientHeight;
    };
    window.addEventListener("resize", handleResize);

    let satProgress = 0.4;

    const render = () => {
      // Smooth continuous slow rotation
      rotRef.current.y += 0.0025;
      const rotX = rotRef.current.x;
      const rotY = rotRef.current.y;

      ctx.clearRect(0, 0, width, height);

      const cx = width / 2;
      const cy = height / 2;
      const radius = Math.min(width, height) * 0.34;

      // Helper 3D Projection
      const project = (x: number, y: number, z: number) => {
        // Rotate Y
        const cosY = Math.cos(rotY);
        const sinY = Math.sin(rotY);
        const x1 = x * cosY - z * sinY;
        const z1 = z * cosY + x * sinY;

        // Rotate X
        const cosX = Math.cos(rotX);
        const sinX = Math.sin(rotX);
        const y2 = y * cosX - z1 * sinX;
        const z2 = z1 * cosX + y * sinX;

        const fov = 750;
        const scale = fov / (fov + z2);
        return {
          x: cx + x1 * scale,
          y: cy + y2 * scale,
          z: z2,
        };
      };

      // Globe Outer Ring / Silhouette (Fine muted green)
      ctx.strokeStyle = "rgba(34, 197, 94, 0.45)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.stroke();

      // Latitude Rings (Clean fine wireframe)
      const latSteps = [-60, -40, -20, 0, 20, 40, 60];
      latSteps.forEach((latDeg) => {
        const phi = (latDeg * Math.PI) / 180;
        const rLat = radius * Math.cos(phi);
        const yLat = radius * Math.sin(phi);

        ctx.beginPath();
        let first = true;
        for (let lonDeg = 0; lonDeg <= 360; lonDeg += 5) {
          const theta = (lonDeg * Math.PI) / 180;
          const x = rLat * Math.cos(theta);
          const z = rLat * Math.sin(theta);
          const p = project(x, yLat, z);

          if (first) {
            ctx.moveTo(p.x, p.y);
            first = false;
          } else {
            ctx.lineTo(p.x, p.y);
          }
        }
        ctx.strokeStyle = latDeg === 0 ? "rgba(34, 197, 94, 0.5)" : "rgba(34, 197, 94, 0.22)";
        ctx.lineWidth = latDeg === 0 ? 1.1 : 0.75;
        ctx.stroke();
      });

      // Longitude Meridians (Fine wireframe)
      for (let lonDeg = 0; lonDeg < 180; lonDeg += 30) {
        const theta = (lonDeg * Math.PI) / 180;
        ctx.beginPath();
        let first = true;
        for (let latDeg = -90; latDeg <= 90; latDeg += 5) {
          const phi = (latDeg * Math.PI) / 180;
          const rLat = radius * Math.cos(phi);
          const y = radius * Math.sin(phi);
          const x = rLat * Math.cos(theta);
          const z = rLat * Math.sin(theta);
          const p = project(x, y, z);

          if (first) {
            ctx.moveTo(p.x, p.y);
            first = false;
          } else {
            ctx.lineTo(p.x, p.y);
          }
        }
        ctx.strokeStyle = "rgba(34, 197, 94, 0.22)";
        ctx.lineWidth = 0.75;
        ctx.stroke();
      }

      // Orbital Elliptical Path 1 (Dotted)
      const orbRadius1 = radius + 55;
      const inclination1 = 0.42;
      ctx.beginPath();
      for (let a = 0; a <= Math.PI * 2; a += 0.05) {
        const rx = orbRadius1 * Math.cos(a);
        const ry = orbRadius1 * Math.sin(a) * Math.sin(inclination1);
        const rz = orbRadius1 * Math.sin(a) * Math.cos(inclination1);
        const pt = project(rx, ry, rz);
        if (a === 0) ctx.moveTo(pt.x, pt.y);
        else ctx.lineTo(pt.x, pt.y);
      }
      ctx.setLineDash([3, 4]);
      ctx.strokeStyle = "rgba(34, 197, 94, 0.28)";
      ctx.lineWidth = 0.9;
      ctx.stroke();
      ctx.setLineDash([]);

      // Orbital Elliptical Path 2
      const orbRadius2 = radius + 75;
      const inclination2 = -0.55;
      ctx.beginPath();
      for (let a = 0; a <= Math.PI * 2; a += 0.05) {
        const rx = orbRadius2 * Math.cos(a);
        const ry = orbRadius2 * Math.sin(a) * Math.sin(inclination2);
        const rz = orbRadius2 * Math.sin(a) * Math.cos(inclination2);
        const pt = project(rx, ry, rz);
        if (a === 0) ctx.moveTo(pt.x, pt.y);
        else ctx.lineTo(pt.x, pt.y);
      }
      ctx.setLineDash([2, 5]);
      ctx.strokeStyle = "rgba(56, 189, 248, 0.25)";
      ctx.lineWidth = 0.8;
      ctx.stroke();
      ctx.setLineDash([]);

      // Orbiting Satellite Node (Cyan dot)
      satProgress = (satProgress + 0.0035) % 1;
      const satAngle = satProgress * Math.PI * 2;
      const satX = orbRadius1 * Math.cos(satAngle);
      const satY = orbRadius1 * Math.sin(satAngle) * Math.sin(inclination1);
      const satZ = orbRadius1 * Math.sin(satAngle) * Math.cos(inclination1);
      const satPt = project(satX, satY, satZ);

      ctx.fillStyle = "#38bdf8";
      ctx.beginPath();
      ctx.arc(satPt.x, satPt.y, 3.5, 0, Math.PI * 2);
      ctx.fill();

      // Ground Target Pin & Badge (Matching Reference Screenshot: LOC: IN-EAST ACQUIRING ✔)
      const targetPhi = (28.55 * Math.PI) / 180;
      const targetTheta = (77.25 * Math.PI) / 180;
      const tx = radius * Math.cos(targetPhi) * Math.cos(targetTheta);
      const ty = radius * Math.sin(targetPhi);
      const tz = radius * Math.cos(targetPhi) * Math.sin(targetTheta);
      const tgtPt = project(tx, ty, tz);

      if (tgtPt.z > -radius * 0.2) {
        // Outer target ring
        ctx.strokeStyle = "#22c55e";
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.arc(tgtPt.x, tgtPt.y, 6, 0, Math.PI * 2);
        ctx.stroke();

        // Inner solid dot
        ctx.fillStyle = "#22c55e";
        ctx.beginPath();
        ctx.arc(tgtPt.x, tgtPt.y, 2.5, 0, Math.PI * 2);
        ctx.fill();

        // Leader line
        const tagX = tgtPt.x + 16;
        const tagY = tgtPt.y - 12;
        ctx.strokeStyle = "rgba(34, 197, 94, 0.6)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(tgtPt.x + 6, tgtPt.y);
        ctx.lineTo(tagX, tagY);
        ctx.lineTo(tagX + 90, tagY);
        ctx.stroke();

        // Tag Box Background
        ctx.fillStyle = "#000000";
        ctx.strokeStyle = "rgba(34, 197, 94, 0.4)";
        ctx.lineWidth = 0.8;
        ctx.fillRect(tagX, tagY - 14, 90, 22);
        ctx.strokeRect(tagX, tagY - 14, 90, 22);

        // Tag text
        ctx.font = "bold 8px 'JetBrains Mono', monospace";
        ctx.fillStyle = "#ffffff";
        ctx.fillText("LOC: IN-EAST", tagX + 6, tagY - 3);
        ctx.fillStyle = "#22c55e";
        ctx.fillText("ACQUIRING ✔", tagX + 6, tagY + 5);
      }

      animationFrameId = requestAnimationFrame(render);
    };

    render();

    const handleMouseDown = (e: MouseEvent) => {
      mouseRef.current.isDragging = true;
      mouseRef.current.lastX = e.clientX;
      mouseRef.current.lastY = e.clientY;
    };

    const handleMouseMove = (e: MouseEvent) => {
      if (mouseRef.current.isDragging) {
        const dx = e.clientX - mouseRef.current.lastX;
        const dy = e.clientY - mouseRef.current.lastY;
        rotRef.current.y += dx * 0.005;
        rotRef.current.x += dy * 0.005;
        mouseRef.current.lastX = e.clientX;
        mouseRef.current.lastY = e.clientY;
      }
    };

    const handleMouseUp = () => {
      mouseRef.current.isDragging = false;
    };

    canvas.addEventListener("mousedown", handleMouseDown);
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener("resize", handleResize);
      canvas.removeEventListener("mousedown", handleMouseDown);
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, []);

  return (
    <div className="relative w-full h-full min-h-[440px] flex items-center justify-center select-none">
      {/* 3D Canvas */}
      <canvas ref={canvasRef} className="w-full h-full cursor-grab active:cursor-grabbing z-10" />

      {/* Telemetry Block (Matching Top-Right of Reference Screenshot) */}
      <div className="absolute top-2 right-2 md:top-4 md:right-4 z-20 font-mono text-[10px] sm:text-[11px] leading-relaxed text-neutral-400 space-y-1 text-left select-none pointer-events-none">
        <div className="flex gap-2">
          <span className="text-neutral-500">TARGET ID:</span>
          <span className="text-neutral-300">CARTOSAT-3</span>
        </div>
        <div className="flex gap-2">
          <span className="text-neutral-500">ALTITUDE:</span>
          <span className="text-neutral-300">509 KM</span>
        </div>
        <div className="flex gap-2">
          <span className="text-neutral-500">CRS:</span>
          <span className="text-neutral-300">EPSG:32645</span>
        </div>
        <div className="flex gap-2">
          <span className="text-neutral-500">STATUS:</span>
          <span className="text-radar font-medium">TELEMETRY LOCK ACTIVE</span>
        </div>
      </div>
    </div>
  );
}

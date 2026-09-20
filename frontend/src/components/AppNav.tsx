import {NavLink} from 'react-router-dom';
import type {ReactNode} from 'react';

export function AppNav(props:{
  onExport:()=>void;
  exportDisabled?:boolean;
  trailing?:ReactNode;
}){
  return (
    <header className="product-nav">
      <NavLink to="/" className="brand">
        <span className="brand-mark" aria-hidden="true"/>
        <div>
          <div className="eyebrow">SEWER SAM2</div>
          <strong>Annotator</strong>
        </div>
      </NavLink>
      <nav className="product-links">
        <NavLink to="/" end>Dashboard</NavLink>
        <NavLink to="/projects">Projects</NavLink>
      </nav>
      <div className="header-actions">
        {props.trailing}
        <button className="button" onClick={props.onExport} disabled={props.exportDisabled}>Export</button>
      </div>
    </header>
  );
}

import { Routes } from '@angular/router';
import { DealComponent } from './pages/deal/deal.component';
import { FreeComponent } from './pages/free/free.component';
import { GameComponent } from './pages/game/game.component';

export const routes: Routes = [
    { path: 'deals', component: DealComponent },
    { path: 'free', component: FreeComponent },
    { path: 'game/:slug', component: GameComponent },
];

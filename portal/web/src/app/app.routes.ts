import { Routes } from '@angular/router';
import { FeedComponent } from './components/feed/feed.component';
import { PostDetailComponent } from './components/post-detail/post-detail.component';

export const routes: Routes = [
  {
    path: '',
    component: FeedComponent,
    title: 'Mind Decoded | Daily Psychology & Artificial Intelligence'
  },
  {
    path: 'posts/:slug',
    component: PostDetailComponent,
    title: 'Article Reflection | Psychology & AI Portal'
  },
  {
    path: '**',
    redirectTo: ''
  }
];


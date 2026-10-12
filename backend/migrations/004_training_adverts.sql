-- 004_training_adverts: a third kind of advert poster.
--
-- Reed lists many training and recruitment companies as "direct employers". An advert that sells
-- a training programme is not a job: it is kept apart, never scored, never looked up on the
-- sponsor register and left out of the role family figures. See jobs.poster.

alter table job_listings drop constraint job_listings_posted_by_check;
alter table job_listings add constraint job_listings_posted_by_check check (posted_by in ('employer', 'agency', 'training'));
